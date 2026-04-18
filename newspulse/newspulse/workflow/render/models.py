# coding=utf-8
"""Native render view models shared by the HTML and notification adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from newspulse.core.analyzer import calculate_news_weight
from newspulse.utils.time import convert_time_for_display
from newspulse.workflow.shared.contracts import (
    DeliveryPayload,
    HotlistItem,
    InsightResult,
    LocalizedReport,
    SelectionGroup,
    StandaloneSection,
)


DEFAULT_RENDER_REGIONS = [
    "hotlist",
    "new_items",
    "standalone",
    "insight",
]

REPORT_TYPE_BY_MODE = {
    "daily": "每日报告",
    "current": "实时报告",
    "incremental": "增量报告",
}

DEFAULT_WEIGHT_CONFIG = {
    "RANK_WEIGHT": 0.6,
    "FREQUENCY_WEIGHT": 0.3,
    "HOTNESS_WEIGHT": 0.1,
}


@dataclass(frozen=True)
class RenderReportMeta:
    """Normalized report metadata assembled before localization/rendering."""

    mode: str
    generated_at: str
    report_type: str
    timezone: str = ""
    display_mode: str = "keyword"
    selection_strategy: str = ""
    insight_strategy: str = ""
    total_items: int = 0
    total_selected: int = 0
    total_new_items: int = 0
    total_standalone_sections: int = 0
    total_failed_sources: int = 0
    snapshot_summary: dict[str, Any] = field(default_factory=dict)
    selection_diagnostics: dict[str, Any] = field(default_factory=dict)
    insight_diagnostics: dict[str, Any] = field(default_factory=dict)
    failed_sources: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert the normalized metadata to the public report shape."""

        return {
            "mode": self.mode,
            "generated_at": self.generated_at,
            "report_type": self.report_type,
            "timezone": self.timezone,
            "display_mode": self.display_mode,
            "selection_strategy": self.selection_strategy,
            "insight_strategy": self.insight_strategy,
            "total_items": self.total_items,
            "total_selected": self.total_selected,
            "total_new_items": self.total_new_items,
            "total_standalone_sections": self.total_standalone_sections,
            "total_failed_sources": self.total_failed_sources,
            "snapshot_summary": dict(self.snapshot_summary),
            "selection_diagnostics": dict(self.selection_diagnostics),
            "insight_diagnostics": dict(self.insight_diagnostics),
            "failed_sources": [dict(item) for item in self.failed_sources],
        }


@dataclass(frozen=True)
class RenderTitleView:
    """Normalized hotlist item used by the render layer."""

    news_item_id: str
    title: str
    source_id: str = ""
    source_name: str = ""
    url: str = ""
    mobile_url: str = ""
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
class RenderInsightSectionView:
    """Localized insight block used by both HTML and notification rendering."""

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

        return bool(self.sections or self.message)


@dataclass(frozen=True)
class RenderViewModel:
    """Native render view model built from the localized workflow report."""

    meta: dict[str, Any] = field(default_factory=dict)
    display_regions: list[str] = field(default_factory=list)
    display_mode: str = "keyword"
    rank_threshold: int = 10
    total_titles: int = 0
    failed_source_names: list[str] = field(default_factory=list)
    hotlist_groups: list[RenderGroupView] = field(default_factory=list)
    new_item_groups: list[RenderGroupView] = field(default_factory=list)
    standalone_groups: list[RenderGroupView] = field(default_factory=list)
    insight: RenderInsightView = field(default_factory=RenderInsightView)
    language: str = ""
    translation_meta: dict[str, Any] = field(default_factory=dict)

    @property
    def mode(self) -> str:
        return str(self.meta.get("mode", "daily"))

    @property
    def report_type(self) -> str:
        return str(self.meta.get("report_type", REPORT_TYPE_BY_MODE.get(self.mode, "热点报告")))

    @property
    def total_new_items(self) -> int:
        return sum(len(group.items) for group in self.new_item_groups)


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
    report: LocalizedReport,
    *,
    display_mode: str = "keyword",
    rank_threshold: int = 50,
    weight_config: dict[str, float] | None = None,
    convert_time_func: Callable[[str], str] = convert_time_for_display,
) -> RenderViewModel:
    """Build the native render view model from the localized workflow report."""

    base_report = report.base_report
    meta = dict(base_report.meta or {})
    mode = str(meta.get("mode", "daily"))
    meta.setdefault("mode", mode)
    meta.setdefault("report_type", REPORT_TYPE_BY_MODE.get(mode, "热点报告"))
    meta.setdefault("display_mode", display_mode)

    hotlist_groups = _build_hotlist_groups(
        base_report.selection.groups,
        report.localized_titles,
        display_mode=display_mode,
        rank_threshold=rank_threshold,
        weight_config=weight_config,
        convert_time_func=convert_time_func,
    )
    new_item_groups = _build_source_groups(
        base_report.new_items,
        report.localized_titles,
        rank_threshold=rank_threshold,
        convert_time_func=convert_time_func,
    )
    standalone_groups = _build_standalone_groups(
        base_report.standalone_sections,
        report.localized_titles,
        rank_threshold=rank_threshold,
        convert_time_func=convert_time_func,
    )
    insight_view = _build_insight_view(
        base_report.insight,
        report.localized_sections,
        total_titles=base_report.selection.total_selected,
        report_meta=meta,
    )

    return RenderViewModel(
        meta=meta,
        display_regions=_normalize_display_regions(base_report.display_regions),
        display_mode=display_mode,
        rank_threshold=rank_threshold,
        total_titles=base_report.selection.total_selected,
        failed_source_names=_build_failed_source_names(meta),
        hotlist_groups=hotlist_groups,
        new_item_groups=new_item_groups,
        standalone_groups=standalone_groups,
        insight=insight_view,
        language=report.language,
        translation_meta=dict(report.translation_meta or {}),
    )


def _normalize_display_regions(display_regions: list[str]) -> list[str]:
    normalized: list[str] = []
    for value in display_regions or DEFAULT_RENDER_REGIONS:
        region = str(value or "").strip().lower()
        if region and region not in normalized:
            normalized.append(region)
    return normalized or list(DEFAULT_RENDER_REGIONS)


def _build_hotlist_groups(
    groups: list[SelectionGroup],
    localized_titles: dict[str, str],
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
                localized_titles,
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
            source_name = item.source_name or item.source_id or "未知来源"
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
    localized_titles: dict[str, str],
    *,
    rank_threshold: int,
    convert_time_func: Callable[[str], str],
) -> list[RenderGroupView]:
    grouped: dict[tuple[str, str], list[RenderTitleView]] = {}
    for item in items:
        title_view = _build_title_view(
            item,
            localized_titles,
            rank_threshold=rank_threshold,
            convert_time_func=convert_time_func,
        )
        source_key = (
            title_view.source_id or item.source_id or title_view.source_name or "unknown",
            title_view.source_name or item.source_name or item.source_id or "未知来源",
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
    localized_titles: dict[str, str],
    *,
    rank_threshold: int,
    convert_time_func: Callable[[str], str],
) -> list[RenderGroupView]:
    groups: list[RenderGroupView] = []
    for index, section in enumerate(sections):
        items = [
            _build_title_view(
                item,
                localized_titles,
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


def _build_insight_view(
    insight: InsightResult,
    localized_sections: dict[str, str],
    *,
    total_titles: int,
    report_meta: dict[str, Any],
) -> RenderInsightView:
    diagnostics = dict(insight.diagnostics or {})
    sections = [
        RenderInsightSectionView(
            key=section.key,
            title=section.title,
            content=localized_sections.get(section.key, section.content),
            summary=section.summary,
            metadata=dict(section.metadata or {}),
        )
        for section in insight.sections
        if str(localized_sections.get(section.key, section.content) or "").strip()
    ]

    message = str(
        diagnostics.get("error")
        or diagnostics.get("parse_error")
        or diagnostics.get("reason")
        or ""
    ).strip()

    if not insight.enabled and insight.strategy == "noop":
        status = "disabled"
    elif diagnostics.get("skipped"):
        status = "skipped"
    elif diagnostics.get("error") or diagnostics.get("parse_error"):
        status = "error"
    elif sections:
        status = "ok"
    elif message:
        status = "error"
    else:
        status = "empty"

    return RenderInsightView(
        status=status,
        message=message,
        sections=sections,
        stats={
            "total_news": total_titles,
            "analyzed_news": int(diagnostics.get("analyzed_items", 0) or 0),
            "max_news_limit": int(diagnostics.get("max_items", 0) or 0),
            "hotlist_count": total_titles,
            "ai_mode": str(diagnostics.get("report_mode", report_meta.get("mode", "")) or ""),
        },
        metadata=diagnostics,
    )


def _build_title_view(
    item: HotlistItem,
    localized_titles: dict[str, str],
    *,
    rank_threshold: int,
    convert_time_func: Callable[[str], str],
    matched_keyword: str = "",
) -> RenderTitleView:
    localized_title = localized_titles.get(str(item.news_item_id), item.title)
    return RenderTitleView(
        news_item_id=str(item.news_item_id),
        title=localized_title,
        source_id=item.source_id,
        source_name=item.source_name,
        url=item.url,
        mobile_url=item.mobile_url,
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
