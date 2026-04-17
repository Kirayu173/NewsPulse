# coding=utf-8
"""Adapters from localized workflow reports to the legacy render payloads."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable

from newspulse.utils.time import convert_time_for_display
from newspulse.workflow.insight import to_ai_analysis_result
from newspulse.workflow.render.models import LegacyRenderContext
from newspulse.workflow.selection.legacy import selection_result_to_legacy_stats
from newspulse.workflow.shared.contracts import (
    HotlistItem,
    InsightResult,
    InsightSection,
    LocalizedReport,
    SelectionGroup,
    SelectionResult,
    StandaloneSection,
)


def localized_report_to_legacy_context(
    report: LocalizedReport,
    *,
    display_mode: str = "keyword",
    rank_threshold: int = 50,
    weight_config: dict[str, float] | None = None,
    convert_time_func: Callable[[str], str] = convert_time_for_display,
) -> LegacyRenderContext:
    """Convert a localized workflow report to the legacy renderer inputs."""

    base_report = report.base_report
    localized_selection = _localize_selection(base_report.selection, report.localized_titles)
    localized_new_items = [_localize_item(item, report.localized_titles) for item in base_report.new_items]
    localized_standalone = _localize_standalone_sections(base_report.standalone_sections, report.localized_titles)
    localized_insight = _localize_insight(base_report.insight, report.localized_sections)

    stats = selection_result_to_legacy_stats(
        localized_selection,
        display_mode=display_mode,
        rank_threshold=rank_threshold,
        weight_config=weight_config,
        convert_time_func=convert_time_func,
    )
    stats = _normalize_legacy_stats(stats)
    report_data = {
        "stats": stats,
        "new_titles": _build_processed_new_items(localized_new_items, rank_threshold, convert_time_func),
        "failed_ids": _build_failed_ids(base_report.meta),
        "total_new_count": len(localized_new_items),
    }
    standalone_data = _build_standalone_data(localized_standalone, convert_time_func)
    ai_analysis = to_ai_analysis_result(
        localized_insight,
        total_news=localized_selection.total_selected,
        analyzed_news=int(localized_insight.diagnostics.get("analyzed_items", 0) or 0),
        max_news_limit=int(localized_insight.diagnostics.get("max_items", 0) or 0),
        hotlist_count=localized_selection.total_selected,
        ai_mode=str(localized_insight.diagnostics.get("report_mode", base_report.meta.get("mode", ""))),
    )
    return LegacyRenderContext(
        report_data=report_data,
        standalone_data=standalone_data,
        ai_analysis=ai_analysis,
        total_titles=localized_selection.total_selected,
        mode=str(base_report.meta.get("mode", "daily")),
        report_type=str(base_report.meta.get("report_type", "热点报告")),
    )


def _localize_selection(selection: SelectionResult, localized_titles: dict[str, str]) -> SelectionResult:
    groups: list[SelectionGroup] = []
    for group in selection.groups:
        groups.append(
            replace(
                group,
                items=[_localize_item(item, localized_titles) for item in group.items],
            )
        )
    return replace(
        selection,
        groups=groups,
        selected_items=[_localize_item(item, localized_titles) for item in selection.selected_items],
        selected_new_items=[_localize_item(item, localized_titles) for item in selection.selected_new_items],
    )


def _localize_standalone_sections(
    sections: list[StandaloneSection],
    localized_titles: dict[str, str],
) -> list[StandaloneSection]:
    return [
        replace(section, items=[_localize_item(item, localized_titles) for item in section.items])
        for section in sections
    ]


def _localize_insight(insight: InsightResult, localized_sections: dict[str, str]) -> InsightResult:
    sections: list[InsightSection] = []
    for section in insight.sections:
        translated = localized_sections.get(section.key)
        if translated:
            sections.append(replace(section, content=translated))
        else:
            sections.append(section)
    return replace(insight, sections=sections)


def _localize_item(item: HotlistItem, localized_titles: dict[str, str]) -> HotlistItem:
    translated = localized_titles.get(item.news_item_id)
    if not translated:
        return item
    return replace(item, title=translated)


def _build_processed_new_items(
    items: list[HotlistItem],
    rank_threshold: int,
    convert_time_func: Callable[[str], str],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in items:
        key = (item.source_id, item.source_name or item.source_id)
        grouped.setdefault(key, []).append(_hotlist_item_to_processed_title(item, rank_threshold, convert_time_func))

    processed: list[dict[str, Any]] = []
    for (source_id, source_name), titles in grouped.items():
        processed.append(
            {
                "source_id": source_id,
                "source_name": source_name,
                "titles": titles,
            }
        )
    return processed


def _normalize_legacy_stats(stats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_stats: list[dict[str, Any]] = []
    for stat in stats:
        normalized_titles: list[dict[str, Any]] = []
        for title in stat.get("titles", []):
            normalized = dict(title)
            normalized["mobile_url"] = normalized.get("mobile_url", normalized.get("mobileUrl", ""))
            normalized["mobileUrl"] = normalized.get("mobileUrl", normalized["mobile_url"])
            normalized_titles.append(normalized)
        normalized_stat = dict(stat)
        normalized_stat["titles"] = normalized_titles
        normalized_stats.append(normalized_stat)
    return normalized_stats


def _build_failed_ids(meta: dict[str, Any]) -> list[str]:
    failed_sources = meta.get("failed_sources", [])
    values: list[str] = []
    for item in failed_sources:
        if isinstance(item, dict):
            values.append(str(item.get("source_name") or item.get("source_id") or "").strip())
        else:
            values.append(str(item).strip())
    return [value for value in values if value]


def _build_standalone_data(
    sections: list[StandaloneSection],
    convert_time_func: Callable[[str], str],
) -> dict[str, Any] | None:
    if not sections:
        return None

    platforms: list[dict[str, Any]] = []
    for section in sections:
        items: list[dict[str, Any]] = []
        for item in section.items:
            items.append(
                {
                    "title": item.title,
                    "url": item.url,
                    "mobileUrl": item.mobile_url,
                    "mobile_url": item.mobile_url,
                    "rank": item.current_rank,
                    "ranks": list(item.ranks),
                    "first_time": item.first_time,
                    "last_time": item.last_time,
                    "count": item.count,
                    "rank_timeline": list(item.rank_timeline),
                    "time_display": _build_time_display(item, convert_time_func),
                }
            )
        platforms.append(
            {
                "id": section.key,
                "name": section.label,
                "items": items,
            }
        )
    return {"platforms": platforms}


def _hotlist_item_to_processed_title(
    item: HotlistItem,
    rank_threshold: int,
    convert_time_func: Callable[[str], str],
) -> dict[str, Any]:
    return {
        "title": item.title,
        "source_name": item.source_name,
        "time_display": _build_time_display(item, convert_time_func),
        "count": item.count,
        "ranks": list(item.ranks),
        "rank_threshold": rank_threshold,
        "url": item.url,
        "mobile_url": item.mobile_url,
        "mobileUrl": item.mobile_url,
        "is_new": item.is_new,
    }


def _build_time_display(item: HotlistItem, convert_time_func: Callable[[str], str]) -> str:
    first_display = convert_time_func(item.first_time) if item.first_time else ""
    last_display = convert_time_func(item.last_time) if item.last_time else ""
    if first_display and last_display and first_display != last_display:
        return f"[{first_display} ~ {last_display}]"
    return first_display or last_display
