# coding=utf-8
"""Validation helpers for Stage 6 report package assembly."""

from __future__ import annotations

from newspulse.workflow.shared.contracts import (
    HotlistSnapshot,
    InsightResult,
    ReportContent,
    ReportIntegrity,
    SelectionResult,
)


class ReportPackageValidator:
    """Validate assembled report content and compute integrity metadata."""

    def validate(
        self,
        snapshot: HotlistSnapshot,
        selection: SelectionResult,
        insight: InsightResult,
        content: ReportContent,
        *,
        resolved_selected_item_ids: set[str],
    ) -> ReportIntegrity:
        warnings: list[str] = []
        errors: list[str] = []
        skipped_regions = self._build_skipped_regions(content, insight)

        snapshot_item_ids = [str(item.news_item_id) for item in snapshot.items]
        snapshot_item_id_set = set(snapshot_item_ids)

        duplicate_snapshot_ids = sorted(self._find_duplicates(snapshot_item_ids))
        if duplicate_snapshot_ids:
            warnings.append(
                "Snapshot contains duplicate item ids: " + ", ".join(duplicate_snapshot_ids)
            )

        missing_selected_ids = sorted(resolved_selected_item_ids - snapshot_item_id_set)
        if missing_selected_ids:
            errors.append(
                "Selection contains items missing from snapshot: " + ", ".join(missing_selected_ids)
            )

        empty_insight_keys: list[str] = []
        duplicate_insight_keys: set[str] = set()
        seen_insight_keys: set[str] = set()

        for section in insight.sections:
            key = str(section.key or "").strip()
            content_text = str(section.content or "").strip()
            if not key:
                empty_insight_keys.append("<empty>")
                continue
            if key in seen_insight_keys:
                duplicate_insight_keys.add(key)
                continue
            seen_insight_keys.add(key)
            if not content_text:
                empty_insight_keys.append(key)

        if duplicate_insight_keys:
            errors.append(
                "Insight contains duplicate section keys: " + ", ".join(sorted(duplicate_insight_keys))
            )
        if empty_insight_keys:
            warnings.append(
                "Insight contains empty section keys or content: " + ", ".join(empty_insight_keys)
            )
        if selection.total_selected and selection.total_selected != len(resolved_selected_item_ids):
            warnings.append(
                "Selection total_selected does not match resolved selected item count."
            )

        counters = {
            "snapshot_item_count": len(snapshot.items),
            "selected_item_count": len(content.selected_items),
            "selected_new_item_count": len(content.new_items),
            "hotlist_group_count": len(content.hotlist_groups),
            "new_item_count": len(content.new_items),
            "standalone_section_count": len(content.standalone_sections),
            "summary_card_count": len(content.summary_cards),
            "insight_section_count": len(content.insight_sections),
            "failed_source_count": len(snapshot.failed_sources),
            "skipped_region_count": len(skipped_regions),
        }

        return ReportIntegrity(
            valid=not errors,
            warnings=warnings,
            errors=errors,
            skipped_regions=skipped_regions,
            counters=counters,
        )

    @staticmethod
    def _find_duplicates(values: list[str]) -> set[str]:
        duplicates: set[str] = set()
        seen: set[str] = set()
        for value in values:
            if value in seen:
                duplicates.add(value)
                continue
            seen.add(value)
        return duplicates

    @staticmethod
    def _build_skipped_regions(content: ReportContent, insight: InsightResult) -> list[str]:
        skipped_regions: list[str] = []
        if not content.selected_items and not any(group.items for group in content.hotlist_groups):
            skipped_regions.append("hotlist")
        if not content.new_items:
            skipped_regions.append("new_items")
        if not any(section.items for section in content.standalone_sections):
            skipped_regions.append("standalone")

        insight_message = str(
            insight.diagnostics.get("error")
            or insight.diagnostics.get("parse_error")
            or insight.diagnostics.get("reason")
            or ""
        ).strip()
        if not content.insight_sections and not insight_message:
            skipped_regions.append("insight")
        return skipped_regions
