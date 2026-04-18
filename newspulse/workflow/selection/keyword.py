# coding=utf-8
"""Keyword-based selection strategy."""

from __future__ import annotations

from typing import Any

from newspulse.workflow.selection.frequency import _word_matches, load_frequency_words
from newspulse.workflow.shared.scoring import calculate_news_weight
from newspulse.workflow.selection.models import KeywordGroupBucket, KeywordGroupDefinition
from newspulse.workflow.shared.contracts import HotlistItem, SelectionGroup, SelectionResult
from newspulse.workflow.shared.options import SelectionOptions

DEFAULT_WEIGHT_CONFIG = {
    "RANK_WEIGHT": 0.6,
    "FREQUENCY_WEIGHT": 0.3,
    "HOTNESS_WEIGHT": 0.1,
}


class KeywordSelectionStrategy:
    """Select hotlist items by configured keyword groups."""

    def __init__(
        self,
        *,
        config_root: str | None = None,
        rank_threshold: int = 50,
        weight_config: dict[str, float] | None = None,
        max_news_per_keyword: int = 0,
        sort_by_position_first: bool = False,
    ):
        self.config_root = config_root
        self.rank_threshold = rank_threshold
        merged_weight_config = dict(DEFAULT_WEIGHT_CONFIG)
        if weight_config:
            merged_weight_config.update(weight_config)
        self.weight_config = merged_weight_config
        self.max_news_per_keyword = max_news_per_keyword
        self.sort_by_position_first = sort_by_position_first

    def run(self, snapshot: Any, options: SelectionOptions) -> SelectionResult:
        """Run keyword selection against a snapshot."""

        raw_groups, filter_words, global_filters = load_frequency_words(
            options.frequency_file,
            config_root=self.config_root,
        )
        group_definitions = self._build_group_definitions(raw_groups)
        buckets = [KeywordGroupBucket(definition=definition) for definition in group_definitions]

        for item in snapshot.items:
            bucket = self._find_bucket(item.title, buckets, filter_words, global_filters)
            if bucket is not None:
                bucket.matched_items.append(item)

        output_groups = self._build_output_groups(buckets, len(snapshot.items))
        selected_items = self._flatten_selected_items(output_groups)
        total_matched = sum(bucket.total_matched for bucket in buckets)

        result = SelectionResult(
            strategy="keyword",
            groups=output_groups,
            selected_items=selected_items,
            total_candidates=len(snapshot.items),
            total_selected=len(selected_items),
            diagnostics={
                "mode": snapshot.mode,
                "frequency_file": options.frequency_file or "frequency_words.txt",
                "filter_words_count": len(filter_words),
                "global_filters_count": len(global_filters),
                "group_count": len(output_groups),
                "matched_candidates": total_matched,
                "sort_by_position_first": self.sort_by_position_first,
            },
        )
        result.selected_new_items = result.resolve_selected_new_items(getattr(snapshot, "new_items", []))
        return result

    def _build_group_definitions(self, raw_groups: list[dict[str, Any]]) -> list[KeywordGroupDefinition]:
        if not raw_groups:
            return [
                KeywordGroupDefinition(
                    group_key="all-news",
                    label="全部新闻",
                    position=0,
                    max_items=self.max_news_per_keyword,
                    required=[],
                    normal=[],
                )
            ]

        definitions: list[KeywordGroupDefinition] = []
        for index, group in enumerate(raw_groups):
            definitions.append(
                KeywordGroupDefinition(
                    group_key=str(group.get("group_key", "")).strip() or f"group-{index + 1}",
                    label=str(group.get("display_name") or group.get("group_key") or f"分组 {index + 1}"),
                    position=index,
                    max_items=int(group.get("max_count", 0) or 0),
                    required=list(group.get("required", [])),
                    normal=list(group.get("normal", [])),
                )
            )
        return definitions

    def _find_bucket(
        self,
        title: str,
        buckets: list[KeywordGroupBucket],
        filter_words: list[Any],
        global_filters: list[str],
    ) -> KeywordGroupBucket | None:
        title_lower = title.lower()

        for global_word in global_filters:
            if str(global_word).lower() in title_lower:
                return None

        for filter_word in filter_words:
            if _word_matches(filter_word, title_lower):
                return None

        for bucket in buckets:
            required_words = bucket.definition.required
            normal_words = bucket.definition.normal

            if required_words and not all(_word_matches(word, title_lower) for word in required_words):
                continue
            if normal_words and not any(_word_matches(word, title_lower) for word in normal_words):
                continue
            return bucket
        return None

    def _build_output_groups(
        self,
        buckets: list[KeywordGroupBucket],
        total_candidates: int,
    ) -> list[SelectionGroup]:
        groups: list[SelectionGroup] = []
        for bucket in buckets:
            sorted_items = sorted(bucket.matched_items, key=self._item_sort_key)
            item_limit = bucket.definition.max_items or self.max_news_per_keyword
            if item_limit > 0:
                sorted_items = sorted_items[:item_limit]
            if not sorted_items:
                continue

            groups.append(
                SelectionGroup(
                    key=bucket.definition.group_key,
                    label=bucket.definition.label,
                    position=bucket.definition.position,
                    items=sorted_items,
                    metadata={
                        "total_matched": bucket.total_matched,
                        "total_selected": len(sorted_items),
                        "percentage": round(bucket.total_matched / total_candidates * 100, 2)
                        if total_candidates
                        else 0,
                    },
                )
            )

        if self.sort_by_position_first:
            groups.sort(key=lambda group: (group.position, -int(group.metadata.get("total_matched", 0))))
        else:
            groups.sort(
                key=lambda group: (
                    -int(group.metadata.get("total_matched", 0)),
                    group.position,
                )
            )
        return groups

    def _flatten_selected_items(self, groups: list[SelectionGroup]) -> list[HotlistItem]:
        seen_ids: set[str] = set()
        selected_items: list[HotlistItem] = []
        for group in groups:
            for item in group.items:
                if item.news_item_id in seen_ids:
                    continue
                seen_ids.add(item.news_item_id)
                selected_items.append(item)
        return selected_items

    def _item_sort_key(self, item: HotlistItem) -> tuple[float, int, int, str]:
        weight = calculate_news_weight(
            {"ranks": list(item.ranks), "count": item.count},
            self.rank_threshold,
            self.weight_config,
        )
        best_rank = min(item.ranks) if item.ranks else 999
        return (-weight, best_rank, -item.count, item.title)
