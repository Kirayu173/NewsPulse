# coding=utf-8
"""Adapters from native selection output to legacy report stats."""

from __future__ import annotations

from typing import Callable

from newspulse.core.analyzer import convert_keyword_stats_to_platform_stats
from newspulse.utils.time import convert_time_for_display
from newspulse.workflow.shared.contracts import HotlistItem, SelectionResult

DEFAULT_WEIGHT_CONFIG = {
    "RANK_WEIGHT": 0.6,
    "FREQUENCY_WEIGHT": 0.3,
    "HOTNESS_WEIGHT": 0.1,
}


def selection_result_to_legacy_stats(
    selection: SelectionResult,
    *,
    display_mode: str = "keyword",
    rank_threshold: int = 50,
    weight_config: dict[str, float] | None = None,
    convert_time_func: Callable[[str], str] = convert_time_for_display,
) -> list[dict]:
    """Convert native selection output into the legacy stats structure."""

    keyword_stats = _selection_result_to_keyword_stats(
        selection,
        rank_threshold=rank_threshold,
        convert_time_func=convert_time_func,
    )
    if display_mode == "platform":
        merged_weight_config = dict(DEFAULT_WEIGHT_CONFIG)
        if weight_config:
            merged_weight_config.update(weight_config)
        return convert_keyword_stats_to_platform_stats(
            keyword_stats,
            merged_weight_config,
            rank_threshold,
        )
    return keyword_stats


def _selection_result_to_keyword_stats(
    selection: SelectionResult,
    *,
    rank_threshold: int,
    convert_time_func: Callable[[str], str],
) -> list[dict]:
    stats: list[dict] = []
    for group in selection.groups:
        titles = [
            _hotlist_item_to_legacy_title(
                item,
                rank_threshold=rank_threshold,
                matched_keyword=group.label,
                convert_time_func=convert_time_func,
            )
            for item in group.items
        ]
        stats.append(
            {
                "word": group.label,
                "count": int(group.metadata.get("total_matched", len(group.items))),
                "position": group.position,
                "titles": titles,
                "percentage": group.metadata.get("percentage", 0),
            }
        )
    return stats


def _hotlist_item_to_legacy_title(
    item: HotlistItem,
    *,
    rank_threshold: int,
    matched_keyword: str,
    convert_time_func: Callable[[str], str],
) -> dict:
    time_display = ""
    first_display = convert_time_func(item.first_time) if item.first_time else ""
    last_display = convert_time_func(item.last_time) if item.last_time else ""
    if first_display and last_display and first_display != last_display:
        time_display = f"[{first_display} ~ {last_display}]"
    elif first_display:
        time_display = first_display

    return {
        "title": item.title,
        "source_name": item.source_name,
        "time_display": time_display,
        "count": item.count,
        "ranks": list(item.ranks),
        "rank_threshold": rank_threshold,
        "url": item.url,
        "mobileUrl": item.mobile_url,
        "is_new": item.is_new,
        "matched_keyword": matched_keyword,
        "rank_timeline": list(item.rank_timeline),
    }
