# coding=utf-8
"""Native render view models shared by the HTML and notification adapters."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable

from newspulse.utils.time import convert_time_for_display
from newspulse.workflow.report import DEFAULT_REPORT_TYPE, REPORT_TYPE_BY_MODE
from newspulse.workflow.shared.contracts import (
    DeliveryPayload,
    HotlistItem,
    InsightSection,
    InsightSummary,
    ReportPackage,
    SelectionGroup,
    StandaloneSection,
)
from newspulse.workflow.shared.scoring import DEFAULT_WEIGHT_CONFIG, calculate_news_weight

DEFAULT_RENDER_REGIONS = [
    "hotlist",
    "new_items",
    "standalone",
    "insight",
]

@dataclass(frozen=True)
class RenderTitleView:
    """Normalized hotlist item used by the render layer."""

    news_item_id: str
    title: str
    source_id: str = ""
    source_name: str = ""
    url: str = ""
    mobile_url: str = ""
    summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    current_rank: int = 0
    ranks: list[int] = field(default_factory=list)
    time_display: str = ""
    count: int = 1
    is_new: bool = False
    matched_keyword: str = ""
    rank_threshold: int = 10
    rank_timeline: list[dict[str, Any]] = field(default_factory=list)

    @property
    def effective_ranks(self) -> list[int]:
        """Return the rank list used by the renderers."""

        if self.ranks:
            return list(self.ranks)
        if self.current_rank > 0:
            return [self.current_rank]
        return []

    @property
    def link_url(self) -> str:
        """Return the best link target for HTML and notification rendering."""

        return self.mobile_url or self.url

    def to_formatter_payload(self) -> dict[str, Any]:
        """Adapt the native title view to the shared title formatter payload."""

        return {
            "title": self.title,
            "source_name": self.source_name,
            "time_display": self.time_display,
            "count": self.count,
            "ranks": self.effective_ranks,
            "rank_threshold": self.rank_threshold,
            "url": self.url,
            "mobile_url": self.mobile_url,
            "mobileUrl": self.mobile_url,
            "is_new": self.is_new,
            "matched_keyword": self.matched_keyword,
            "rank_timeline": [dict(item) for item in self.rank_timeline],
        }


@dataclass(frozen=True)
class RenderGroupView:
    """Generic grouped collection used by hotlist, new-item and standalone sections."""

    key: str
    label: str
    items: list[RenderTitleView] = field(default_factory=list)
    count: int = 0
    description: str = ""
    position: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RenderSelectionEvidenceView:
    """Selection-funnel evidence shown on the HTML news card."""

    matched_topics: list[str] = field(default_factory=list)
    llm_reasons: list[str] = field(default_factory=list)
    evidence: str = ""
    semantic_score: float = 0.0
    quality_score: float = 0.0
    decision_layer: str = ""

    @property
    def visible(self) -> bool:
        return bool(
            self.matched_topics
            or self.llm_reasons
            or self.evidence
            or self.semantic_score > 0
            or self.quality_score > 0
            or self.decision_layer
        )


@dataclass(frozen=True)
class RenderInsightSummaryView:
    """Structured summary card shown before global insight analysis."""

    kind: str = ""
    key: str = ""
    title: str = ""
    summary: str = ""
    item_ids: list[str] = field(default_factory=list)
    evidence_topics: list[str] = field(default_factory=list)
    evidence_notes: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    expanded: bool = True
    attributes: list[str] = field(default_factory=list)
    semantic_score: float = 0.0
    quality_score: float = 0.0
    current_rank: int = 0
    rank_trend: str = ""
    source_kind: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def visible(self) -> bool:
        return bool(
            self.title
            or self.summary
            or self.attributes
            or self.evidence_topics
            or self.evidence_notes
            or self.sources
            or self.semantic_score > 0
            or self.quality_score > 0
            or self.current_rank > 0
            or self.rank_trend
        )


@dataclass(frozen=True)
class RenderNewsCardView:
    """Flat news-card view used by the redesigned HTML report."""

    item: RenderTitleView
    source_summary: str = ""
    source_attributes: list[str] = field(default_factory=list)
    selection_evidence: RenderSelectionEvidenceView = field(default_factory=RenderSelectionEvidenceView)
    summary: RenderInsightSummaryView = field(default_factory=RenderInsightSummaryView)
    is_selected: bool = False
    is_new: bool = False
    is_standalone: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RenderInsightSectionView:
    """Insight block used by both HTML and notification rendering."""

    key: str
    title: str
    content: str
    summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RenderInsightView:
    """Normalized insight payload shared by HTML and notification rendering."""

    status: str = "disabled"
    message: str = ""
    sections: list[RenderInsightSectionView] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def visible(self) -> bool:
        """Return whether the insight region should be rendered."""

        return bool(self.sections) or (
            self.status in {"skipped", "error"} and bool(self.message)
        )


@dataclass(frozen=True)
class RenderViewModel:
    """Native render view model built from the assembled report package."""

    meta: dict[str, Any] = field(default_factory=dict)
    display_mode: str = "keyword"
    rank_threshold: int = 10
    total_titles: int = 0
    failed_source_names: list[str] = field(default_factory=list)
    hotlist_groups: list[RenderGroupView] = field(default_factory=list)
    new_item_groups: list[RenderGroupView] = field(default_factory=list)
    standalone_groups: list[RenderGroupView] = field(default_factory=list)
    news_cards: list[RenderNewsCardView] = field(default_factory=list)
    summary_cards: list[RenderInsightSummaryView] = field(default_factory=list)
    insight: RenderInsightView = field(default_factory=RenderInsightView)

    @property
    def mode(self) -> str:
        return str(self.meta.get("mode", "daily"))

    @property
    def report_type(self) -> str:
        return str(self.meta.get("report_type", REPORT_TYPE_BY_MODE.get(self.mode, DEFAULT_REPORT_TYPE)))

    @property
    def total_new_items(self) -> int:
        return sum(len(group.items) for group in self.new_item_groups)

    @property
    def analyzed_card_count(self) -> int:
        return sum(1 for card in self.news_cards if card.summary.visible)


@dataclass(frozen=True)
class HTMLArtifact:
    """HTML render artifact produced by the render stage."""

    file_path: str = ""
    content: str = ""


@dataclass(frozen=True)
class RenderArtifacts:
    """Combined render outputs used by the downstream delivery stage."""

    html: HTMLArtifact = field(default_factory=HTMLArtifact)
    payloads: list[DeliveryPayload] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def build_render_view_model(
    report: ReportPackage,
    *,
    display_mode: str = "keyword",
    rank_threshold: int = 50,
    weight_config: dict[str, float] | None = None,
    convert_time_func: Callable[[str], str] = convert_time_for_display,
) -> RenderViewModel:
    """Build the native render view model from the assembled report package."""

    mode = str(report.meta.mode or "daily")
    effective_display_mode = display_mode or str(report.meta.display_mode or "keyword")
    selection_meta = deepcopy(report.diagnostics.get("selection", {}))
    insight_meta = deepcopy(report.diagnostics.get("insight", {}))
    meta = {
        "mode": mode,
        "generated_at": report.meta.generated_at,
        "report_type": report.meta.report_type or REPORT_TYPE_BY_MODE.get(mode, DEFAULT_REPORT_TYPE),
        "timezone": report.meta.timezone,
        "display_mode": report.meta.display_mode or effective_display_mode,
        "selection_strategy": report.meta.selection_strategy,
        "insight_strategy": report.meta.insight_strategy,
        "integrity": {
            "valid": report.integrity.valid,
            "warnings": list(report.integrity.warnings),
            "errors": list(report.integrity.errors),
            "skipped_regions": list(report.integrity.skipped_regions),
            "counters": dict(report.integrity.counters),
        },
        "snapshot_summary": deepcopy(report.diagnostics.get("snapshot_summary", {})),
        "selection": selection_meta,
        "insight": insight_meta,
        "failed_sources": [dict(item) for item in report.diagnostics.get("failed_sources", [])],
    }

    hotlist_groups = _build_hotlist_groups(
        report.content.hotlist_groups,
        display_mode=effective_display_mode,
        rank_threshold=rank_threshold,
        weight_config=weight_config,
        convert_time_func=convert_time_func,
    )
    new_item_groups = _build_source_groups(
        report.content.new_items,
        rank_threshold=rank_threshold,
        convert_time_func=convert_time_func,
    )
    standalone_groups = _build_standalone_groups(
        report.content.standalone_sections,
        rank_threshold=rank_threshold,
        convert_time_func=convert_time_func,
    )
    news_cards = _build_news_cards(
        report,
        rank_threshold=rank_threshold,
        convert_time_func=convert_time_func,
    )
    summary_cards = _build_summary_cards(report.content.summary_cards)
    insight_view = _build_insight_view(
        report.content.insight_sections,
        insight_metadata=insight_meta,
        total_titles=len(report.content.selected_items),
        report_meta=meta,
    )

    return RenderViewModel(
        meta=meta,
        display_mode=effective_display_mode,
        rank_threshold=rank_threshold,
        total_titles=len(report.content.selected_items),
        failed_source_names=_build_failed_source_names(meta),
        hotlist_groups=hotlist_groups,
        new_item_groups=new_item_groups,
        standalone_groups=standalone_groups,
        news_cards=news_cards,
        summary_cards=summary_cards,
        insight=insight_view,
    )


def _build_hotlist_groups(
    groups: list[SelectionGroup],
    *,
    display_mode: str,
    rank_threshold: int,
    weight_config: dict[str, float] | None,
    convert_time_func: Callable[[str], str],
) -> list[RenderGroupView]:
    keyword_groups: list[RenderGroupView] = []
    for group in groups:
        items = [
            _build_title_view(
                item,
                rank_threshold=rank_threshold,
                convert_time_func=convert_time_func,
                matched_keyword=group.label,
            )
            for item in group.items
        ]
        keyword_groups.append(
            RenderGroupView(
                key=group.key,
                label=group.label,
                items=items,
                count=int(group.metadata.get("total_matched", len(group.items))),
                description=group.description,
                position=group.position,
                metadata=dict(group.metadata or {}),
            )
        )

    if display_mode != "platform":
        return keyword_groups
    return _build_platform_groups(keyword_groups, rank_threshold=rank_threshold, weight_config=weight_config)


def _build_platform_groups(
    keyword_groups: list[RenderGroupView],
    *,
    rank_threshold: int,
    weight_config: dict[str, float] | None,
) -> list[RenderGroupView]:
    merged_weight_config = dict(DEFAULT_WEIGHT_CONFIG)
    if weight_config:
        merged_weight_config.update(weight_config)

    platform_map: dict[tuple[str, str], list[RenderTitleView]] = {}
    seen_titles: dict[tuple[str, str], set[str]] = {}

    for group in keyword_groups:
        for item in group.items:
            source_id = item.source_id or item.source_name or "unknown"
            source_name = item.source_name or item.source_id or "Unknown"
            platform_key = (source_id, source_name)
            dedupe_key = item.news_item_id or item.title
            seen = seen_titles.setdefault(platform_key, set())
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            platform_map.setdefault(platform_key, []).append(item)

    groups: list[RenderGroupView] = []
    for index, ((source_id, source_name), items) in enumerate(platform_map.items()):
        sorted_items = sorted(
            items,
            key=lambda item: _platform_item_sort_key(item, merged_weight_config),
        )
        groups.append(
            RenderGroupView(
                key=source_id,
                label=source_name,
                items=sorted_items,
                count=len(sorted_items),
                position=index,
            )
        )

    groups.sort(key=lambda group: (-group.count, group.position, group.label.lower()))
    return groups


def _platform_item_sort_key(item: RenderTitleView, weight_config: dict[str, float]) -> tuple[Any, ...]:
    payload = {
        "ranks": item.effective_ranks,
        "count": item.count,
    }
    weight = calculate_news_weight(payload, item.rank_threshold, weight_config)
    min_rank = min(item.effective_ranks) if item.effective_ranks else 999
    return (-weight, min_rank, -item.count, item.title.lower())


def _build_source_groups(
    items: list[HotlistItem],
    *,
    rank_threshold: int,
    convert_time_func: Callable[[str], str],
) -> list[RenderGroupView]:
    grouped: dict[tuple[str, str], list[RenderTitleView]] = {}
    for item in items:
        title_view = _build_title_view(
            item,
            rank_threshold=rank_threshold,
            convert_time_func=convert_time_func,
        )
        source_key = (
            title_view.source_id or item.source_id or title_view.source_name or "unknown",
            title_view.source_name or item.source_name or item.source_id or "Unknown",
        )
        grouped.setdefault(source_key, []).append(title_view)

    groups: list[RenderGroupView] = []
    for index, ((source_id, source_name), group_items) in enumerate(grouped.items()):
        groups.append(
            RenderGroupView(
                key=source_id,
                label=source_name,
                items=group_items,
                count=len(group_items),
                position=index,
            )
        )
    return groups


def _build_standalone_groups(
    sections: list[StandaloneSection],
    *,
    rank_threshold: int,
    convert_time_func: Callable[[str], str],
) -> list[RenderGroupView]:
    groups: list[RenderGroupView] = []
    for index, section in enumerate(sections):
        items = [
            _build_title_view(
                item,
                rank_threshold=rank_threshold,
                convert_time_func=convert_time_func,
            )
            for item in section.items
        ]
        groups.append(
            RenderGroupView(
                key=section.key,
                label=section.label,
                items=items,
                count=len(items),
                description=section.description,
                position=index,
                metadata=dict(section.metadata or {}),
            )
        )
    return groups


def _build_news_cards(
    report: ReportPackage,
    *,
    rank_threshold: int,
    convert_time_func: Callable[[str], str],
) -> list[RenderNewsCardView]:
    selected_items = list(report.content.selected_items or [])
    selected_ids = {str(item.news_item_id or "").strip() for item in selected_items}
    new_ids = {str(item.news_item_id or "").strip() for item in report.content.new_items}
    standalone_rows = _collect_standalone_rows(report.content.standalone_sections)
    standalone_ids = set(standalone_rows)
    group_labels = _build_group_labels_map(report.content.hotlist_groups)

    selection_meta = dict(report.diagnostics.get("selection", {}))
    insight_meta = dict(report.diagnostics.get("insight", {}))
    selection_matches = _build_selection_match_map(selection_meta)
    input_contexts = _build_input_context_map(insight_meta)
    item_summary_payloads = _build_item_summary_map(insight_meta, report.content.summary_cards)

    ordered_items: list[HotlistItem] = list(selected_items)
    seen_ids = {str(item.news_item_id or "").strip() for item in ordered_items}
    for row in standalone_rows.values():
        item = row["item"]
        item_id = str(item.news_item_id or "").strip()
        if item_id in seen_ids:
            continue
        ordered_items.append(item)
        seen_ids.add(item_id)

    cards: list[RenderNewsCardView] = []
    for item in ordered_items:
        item_id = str(item.news_item_id or "").strip()
        if not item_id:
            continue

        context_payload = input_contexts.get(item_id, {})
        summary_payload = item_summary_payloads.get(item_id, {})
        standalone_meta = standalone_rows.get(item_id, {})

        cards.append(
            RenderNewsCardView(
                item=_build_title_view(
                    item,
                    rank_threshold=rank_threshold,
                    convert_time_func=convert_time_func,
                    matched_keyword=", ".join(group_labels.get(item_id, [])),
                ),
                source_summary=_build_source_summary(item, context_payload),
                source_attributes=_coerce_str_list(
                    context_payload.get("source_context", {}).get("attributes", [])
                    if isinstance(context_payload.get("source_context"), dict)
                    else []
                ),
                selection_evidence=_build_selection_evidence_view(
                    context_payload=context_payload,
                    match_payload=selection_matches.get(item_id, {}),
                ),
                summary=_build_summary_view(summary_payload),
                is_selected=item_id in selected_ids,
                is_new=item.is_new or item_id in new_ids,
                is_standalone=item_id in standalone_ids,
                metadata={
                    "group_labels": list(group_labels.get(item_id, [])),
                    "standalone_section_key": str(standalone_meta.get("section_key", "") or ""),
                    "standalone_section_label": str(standalone_meta.get("section_label", "") or ""),
                },
            )
        )
    return cards


def _collect_standalone_rows(
    sections: list[StandaloneSection],
) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for section in sections:
        for item in section.items:
            item_id = str(item.news_item_id or "").strip()
            if not item_id or item_id in rows:
                continue
            rows[item_id] = {
                "item": item,
                "section_key": section.key,
                "section_label": section.label,
            }
    return rows


def _build_group_labels_map(groups: list[SelectionGroup]) -> dict[str, list[str]]:
    labels_by_item: dict[str, list[str]] = {}
    for group in groups:
        label = str(group.label or "").strip()
        if not label:
            continue
        for item in group.items:
            item_id = str(item.news_item_id or "").strip()
            if not item_id:
                continue
            labels = labels_by_item.setdefault(item_id, [])
            if label not in labels:
                labels.append(label)
    return labels_by_item


def _build_selection_match_map(selection_meta: dict[str, Any]) -> dict[str, dict[str, Any]]:
    diagnostics = selection_meta.get("diagnostics", {})
    if not isinstance(diagnostics, dict):
        return {}
    rows = diagnostics.get("selected_matches", [])
    if not isinstance(rows, list):
        return {}

    payload: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        item_id = str(row.get("news_item_id", "") or "").strip()
        if item_id:
            payload[item_id] = dict(row)
    return payload


def _build_input_context_map(insight_meta: dict[str, Any]) -> dict[str, dict[str, Any]]:
    diagnostics = insight_meta.get("diagnostics", {})
    if not isinstance(diagnostics, dict):
        return {}
    rows = diagnostics.get("input_contexts", [])
    if not isinstance(rows, list):
        return {}

    payload: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        item_id = str(row.get("news_item_id", "") or "").strip()
        if item_id:
            payload[item_id] = dict(row)
    return payload


def _build_item_summary_map(
    insight_meta: dict[str, Any],
    summary_cards: list[InsightSummary],
) -> dict[str, dict[str, Any]]:
    payload: dict[str, dict[str, Any]] = {}
    for summary in summary_cards:
        if getattr(summary, "kind", "") != "item":
            continue
        row = _summary_to_payload(summary)
        for item_id in summary.item_ids:
            text = str(item_id or "").strip()
            if text and text not in payload:
                payload[text] = row
    if payload:
        return payload

    diagnostics = insight_meta.get("diagnostics", {})
    if not isinstance(diagnostics, dict):
        return {}
    rows = diagnostics.get("item_summary_payloads", [])
    if not isinstance(rows, list):
        return {}

    for row in rows:
        if not isinstance(row, dict):
            continue
        item_ids = _coerce_str_list(row.get("item_ids", []))
        item_id = item_ids[0] if item_ids else str(row.get("key", "") or "").replace("item:", "", 1).strip()
        if item_id:
            payload[item_id] = dict(row)
    return payload


def _build_source_summary(item: HotlistItem, context_payload: dict[str, Any]) -> str:
    source_context = context_payload.get("source_context", {}) if isinstance(context_payload, dict) else {}
    if isinstance(source_context, dict):
        summary = str(source_context.get("summary", "") or "").strip()
        if summary:
            return summary
    return str(item.summary or "").strip()


def _build_selection_evidence_view(
    *,
    context_payload: dict[str, Any],
    match_payload: dict[str, Any],
) -> RenderSelectionEvidenceView:
    selection_payload = context_payload.get("selection_evidence", {}) if isinstance(context_payload, dict) else {}
    if not isinstance(selection_payload, dict):
        selection_payload = {}

    matched_topics = _coerce_str_list(selection_payload.get("matched_topics", []))
    if not matched_topics:
        matched_topics = _coerce_str_list(match_payload.get("matched_topics", []))

    llm_reasons = _coerce_str_list(selection_payload.get("llm_reasons", []))
    if not llm_reasons:
        llm_reasons = _coerce_str_list(match_payload.get("reasons", []))

    return RenderSelectionEvidenceView(
        matched_topics=matched_topics,
        llm_reasons=llm_reasons,
        evidence=str(match_payload.get("evidence", "") or "").strip(),
        semantic_score=_coerce_float(selection_payload.get("semantic_score", 0.0)),
        quality_score=_coerce_float(
            selection_payload.get("quality_score", match_payload.get("quality_score", 0.0))
        ),
        decision_layer=str(
            selection_payload.get("decision_layer", match_payload.get("decision_layer", "")) or ""
        ).strip(),
    )


def _build_summary_cards(summary_cards: list[InsightSummary]) -> list[RenderInsightSummaryView]:
    return [_build_summary_view(_summary_to_payload(summary)) for summary in summary_cards]


def _summary_to_payload(summary: InsightSummary) -> dict[str, Any]:
    return {
        "kind": summary.kind,
        "key": summary.key,
        "title": summary.title,
        "summary": summary.summary,
        "item_ids": list(summary.item_ids),
        "evidence_topics": list(summary.evidence_topics),
        "evidence_notes": list(summary.evidence_notes),
        "sources": list(summary.sources),
        "expanded": bool(summary.expanded),
        "metadata": dict(summary.metadata or {}),
    }


def _build_summary_view(payload: dict[str, Any]) -> RenderInsightSummaryView:
    if not payload:
        return RenderInsightSummaryView()

    metadata = dict(payload.get("metadata", {}) if isinstance(payload.get("metadata"), dict) else {})
    return RenderInsightSummaryView(
        kind=str(payload.get("kind", "") or "").strip(),
        key=str(payload.get("key", "") or "").strip(),
        title=str(payload.get("title", "") or "").strip(),
        summary=str(payload.get("summary", "") or "").strip(),
        item_ids=_coerce_str_list(payload.get("item_ids", [])),
        evidence_topics=_coerce_str_list(payload.get("evidence_topics", [])),
        evidence_notes=_coerce_str_list(payload.get("evidence_notes", [])),
        sources=_coerce_str_list(payload.get("sources", [])),
        expanded=bool(payload.get("expanded", True)),
        attributes=_coerce_str_list(metadata.get("attributes", [])),
        semantic_score=_coerce_float(metadata.get("semantic_score", 0.0)),
        quality_score=_coerce_float(metadata.get("quality_score", 0.0)),
        current_rank=int(metadata.get("current_rank", 0) or 0),
        rank_trend=str(metadata.get("rank_trend", "") or "").strip(),
        source_kind=str(metadata.get("source_kind", "") or "").strip(),
        metadata=metadata,
    )


def _coerce_str_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    normalized: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            normalized.append(text)
    return normalized


def _coerce_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _build_insight_view(
    sections: list[InsightSection],
    *,
    insight_metadata: dict[str, Any],
    total_titles: int,
    report_meta: dict[str, Any],
) -> RenderInsightView:
    diagnostics = dict(insight_metadata.get("diagnostics", {}))
    enabled = bool(insight_metadata.get("enabled", False))
    strategy = str(
        insight_metadata.get("strategy")
        or report_meta.get("insight_strategy", "")
        or "noop"
    ).strip() or "noop"
    section_views = [
        RenderInsightSectionView(
            key=section.key,
            title=section.title,
            content=section.content,
            summary=section.summary,
            metadata=dict(section.metadata or {}),
        )
        for section in sections
        if str(section.content or "").strip()
    ]

    message = str(
        diagnostics.get("error")
        or diagnostics.get("parse_error")
        or diagnostics.get("reason")
        or ""
    ).strip()

    if diagnostics.get("skipped"):
        status = "skipped"
    elif not enabled and strategy == "noop":
        status = "disabled"
    elif diagnostics.get("error") or diagnostics.get("parse_error"):
        status = "error"
    elif section_views:
        status = "ok"
    elif message:
        status = "error"
    else:
        status = "empty"

    return RenderInsightView(
        status=status,
        message=message,
        sections=section_views,
        stats={
            "total_news": total_titles,
            "analyzed_news": int(diagnostics.get("item_summary_count", insight_metadata.get("summary_count", 0)) or 0),
            "max_news_limit": int(diagnostics.get("max_items", 0) or 0),
            "hotlist_count": total_titles,
            "ai_mode": str(diagnostics.get("report_mode", report_meta.get("mode", "")) or ""),
        },
        metadata=diagnostics,
    )


def _build_title_view(
    item: HotlistItem,
    *,
    rank_threshold: int,
    convert_time_func: Callable[[str], str],
    matched_keyword: str = "",
) -> RenderTitleView:
    return RenderTitleView(
        news_item_id=str(item.news_item_id),
        title=item.title,
        source_id=item.source_id,
        source_name=item.source_name,
        url=item.url,
        mobile_url=item.mobile_url,
        summary=item.summary,
        metadata=deepcopy(item.metadata),
        current_rank=item.current_rank,
        ranks=list(item.ranks),
        time_display=_build_time_display(item, convert_time_func),
        count=item.count,
        is_new=item.is_new,
        matched_keyword=matched_keyword,
        rank_threshold=rank_threshold,
        rank_timeline=[dict(entry) for entry in item.rank_timeline],
    )


def _build_failed_source_names(meta: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for item in meta.get("failed_sources", []):
        if isinstance(item, dict):
            values.append(str(item.get("source_name") or item.get("source_id") or "").strip())
        else:
            values.append(str(item or "").strip())
    return [value for value in values if value]


def _build_time_display(item: HotlistItem, convert_time_func: Callable[[str], str]) -> str:
    first_display = convert_time_func(item.first_time) if item.first_time else ""
    last_display = convert_time_func(item.last_time) if item.last_time else ""
    if first_display and last_display and first_display != last_display:
        return f"[{first_display} ~ {last_display}]"
    return first_display or last_display
