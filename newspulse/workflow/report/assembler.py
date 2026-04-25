# coding=utf-8
"""Stage 6 report package assembly."""

from __future__ import annotations

from copy import deepcopy

from newspulse.workflow.report.validator import ReportPackageValidator
from newspulse.workflow.shared.contracts import (
    HotlistItem,
    HotlistSnapshot,
    InsightResult,
    InsightSection,
    ReportContent,
    ReportPackage,
    ReportPackageMeta,
    SelectionGroup,
    SelectionResult,
    StandaloneSection,
)


REPORT_TYPE_BY_MODE = {
    "daily": "\u6bcf\u65e5\u62a5\u544a",
    "current": "\u5b9e\u65f6\u62a5\u544a",
    "incremental": "\u589e\u91cf\u62a5\u544a",
}

DEFAULT_REPORT_TYPE = "\u70ed\u70b9\u5206\u6790\u62a5\u544a"


class ReportPackageAssembler:
    """Assemble snapshot, selection and insight outputs into a Stage 6 report package."""

    def __init__(
        self,
        *,
        timezone: str = "",
        display_mode: str = "keyword",
        validator: ReportPackageValidator | None = None,
    ):
        self.timezone = timezone
        self.display_mode = display_mode
        self.validator = validator or ReportPackageValidator()

    def assemble(
        self,
        snapshot: HotlistSnapshot,
        selection: SelectionResult,
        insight: InsightResult,
    ) -> ReportPackage:
        """Combine stage outputs into an immutable downstream package."""

        selected_items = list(selection.qualified_items or selection.selected_items or [])
        resolved_selected_item_ids = {
            str(item.news_item_id)
            for item in selected_items
            if str(item.news_item_id or "").strip()
        }
        snapshot_item_map = self._build_snapshot_item_map(snapshot)

        content = ReportContent(
            hotlist_groups=self._build_hotlist_groups(
                selection=selection,
                snapshot_item_map=snapshot_item_map,
            ),
            selected_items=self._copy_known_items(selected_items, snapshot_item_map),
            new_items=self._build_new_items(snapshot.new_items, resolved_selected_item_ids),
            standalone_sections=self._build_standalone_sections(snapshot.standalone_sections),
            insight_sections=self._build_insight_sections(insight.sections),
        )

        integrity = self.validator.validate(
            snapshot,
            selection,
            insight,
            content,
            resolved_selected_item_ids=resolved_selected_item_ids,
        )

        return ReportPackage(
            meta=ReportPackageMeta(
                mode=snapshot.mode,
                report_type=REPORT_TYPE_BY_MODE.get(snapshot.mode, DEFAULT_REPORT_TYPE),
                generated_at=snapshot.generated_at,
                timezone=self.timezone,
                display_mode=self.display_mode,
                selection_strategy=selection.strategy,
                insight_strategy=insight.strategy,
            ),
            content=content,
            integrity=integrity,
            diagnostics={
                "snapshot_summary": deepcopy(snapshot.summary),
                "selection": {
                    "strategy": selection.strategy,
                    "total_candidates": selection.total_candidates,
                    "total_selected": selection.total_selected,
                    "rejected_count": len(selection.rejected_items),
                    "diagnostics": deepcopy(selection.diagnostics),
                },
                "insight": {
                    "enabled": insight.enabled,
                    "strategy": insight.strategy,
                    "brief_count": len(insight.briefs),
                    "raw_response": insight.raw_response,
                    "diagnostics": deepcopy(insight.diagnostics),
                },
                "failed_sources": [
                    {
                        "source_id": item.source_id,
                        "source_name": item.source_name,
                        "reason": item.reason,
                        "resolved_source_id": item.resolved_source_id,
                        "exception_type": item.exception_type,
                        "message": item.message,
                        "attempts": item.attempts,
                    }
                    for item in snapshot.failed_sources
                ],
            },
        )

    @staticmethod
    def _build_snapshot_item_map(snapshot: HotlistSnapshot) -> dict[str, HotlistItem]:
        snapshot_item_map: dict[str, HotlistItem] = {}
        for item in snapshot.items:
            item_id = str(item.news_item_id or "").strip()
            if item_id and item_id not in snapshot_item_map:
                snapshot_item_map[item_id] = item
        return snapshot_item_map

    def _build_hotlist_groups(
        self,
        *,
        selection: SelectionResult,
        snapshot_item_map: dict[str, HotlistItem],
    ) -> list[SelectionGroup]:
        source_groups = list(selection.groups or [])
        if not source_groups:
            source_groups = self._build_source_hotlist_groups(
                self._copy_known_items(
                    list(selection.qualified_items or selection.selected_items or []),
                    snapshot_item_map,
                )
            )

        groups: list[SelectionGroup] = []
        for group in source_groups:
            items = self._copy_known_items(group.items, snapshot_item_map)
            if not items:
                continue
            groups.append(
                SelectionGroup(
                    key=group.key,
                    label=group.label,
                    items=items,
                    description=group.description,
                    position=group.position,
                    metadata=deepcopy(group.metadata),
                )
            )
        return groups

    @staticmethod
    def _build_source_hotlist_groups(items: list[HotlistItem]) -> list[SelectionGroup]:
        grouped: dict[tuple[str, str], list[HotlistItem]] = {}
        ordered_keys: list[tuple[str, str]] = []
        for item in items:
            key = (
                str(item.source_id or item.source_name or "unknown"),
                str(item.source_name or item.source_id or "Unknown"),
            )
            if key not in grouped:
                grouped[key] = []
                ordered_keys.append(key)
            grouped[key].append(item)

        groups: list[SelectionGroup] = []
        for position, key in enumerate(ordered_keys):
            source_id, source_name = key
            groups.append(
                SelectionGroup(
                    key=source_id,
                    label=source_name,
                    items=[deepcopy(item) for item in grouped[key]],
                    position=position,
                    metadata={
                        "group_type": "source",
                        "generated_by_report_package": True,
                    },
                )
            )
        return groups

    @staticmethod
    def _build_new_items(
        snapshot_new_items: list[HotlistItem],
        resolved_selected_item_ids: set[str],
    ) -> list[HotlistItem]:
        return [
            deepcopy(item)
            for item in snapshot_new_items
            if str(item.news_item_id or "").strip() in resolved_selected_item_ids
        ]

    @staticmethod
    def _build_standalone_sections(
        standalone_sections: list[StandaloneSection],
    ) -> list[StandaloneSection]:
        return [deepcopy(section) for section in standalone_sections]

    @staticmethod
    def _build_insight_sections(
        insight_sections: list[InsightSection],
    ) -> list[InsightSection]:
        normalized: list[InsightSection] = []
        seen_keys: set[str] = set()
        for section in insight_sections:
            key = str(section.key or "").strip()
            content = str(section.content or "").strip()
            if not key or not content or key in seen_keys:
                continue
            seen_keys.add(key)
            normalized.append(deepcopy(section))
        return normalized

    @staticmethod
    def _copy_known_items(
        items: list[HotlistItem],
        snapshot_item_map: dict[str, HotlistItem],
    ) -> list[HotlistItem]:
        copied_items: list[HotlistItem] = []
        for item in items:
            item_id = str(item.news_item_id or "").strip()
            if item_id and item_id in snapshot_item_map:
                canonical_item = deepcopy(snapshot_item_map[item_id])
                if item.metadata:
                    merged_metadata = dict(canonical_item.metadata or {})
                    merged_metadata.update(deepcopy(item.metadata))
                    canonical_item.metadata = merged_metadata
                copied_items.append(canonical_item)
        return copied_items
