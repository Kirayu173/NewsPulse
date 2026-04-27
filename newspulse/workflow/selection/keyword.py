# coding=utf-8
"""Rule-based blacklist filter used by the selection funnel."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from newspulse.core.config_paths import DEFAULT_FREQUENCY_WORDS_FILE
from newspulse.workflow.selection.frequency import _word_matches, load_keyword_rule_set
from newspulse.workflow.selection.models import KeywordRuleSet
from newspulse.workflow.shared.contracts import (
    HotlistItem,
    SelectionGroup,
    SelectionRejectedItem,
    SelectionResult,
)
from newspulse.workflow.shared.options import SelectionOptions


@dataclass(frozen=True)
class RuleFilterResult:
    """Rule-filter output before semantic and LLM gating."""

    passed_items: tuple[HotlistItem, ...] = ()
    rejected_items: tuple[SelectionRejectedItem, ...] = ()
    diagnostics: dict[str, Any] = field(default_factory=dict)


class KeywordSelectionStrategy:
    """Apply the keyword config as a blacklist-first rule filter."""

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
        self.weight_config = dict(weight_config or {})
        self.max_news_per_keyword = max_news_per_keyword
        self.sort_by_position_first = sort_by_position_first

    def run(self, snapshot: Any, options: SelectionOptions) -> SelectionResult:
        """Run only the blacklist / low-value filter stage."""

        filter_result = self.filter_items(
            snapshot.items,
            frequency_file=options.frequency_file,
        )
        qualified_items = list(filter_result.passed_items)
        diagnostics = {
            "mode": snapshot.mode,
            "frequency_file": options.frequency_file or DEFAULT_FREQUENCY_WORDS_FILE,
            "passed_count": len(qualified_items),
            "blacklist_rejected_count": len(filter_result.rejected_items),
            "requested_strategy": "keyword",
        }
        diagnostics.update(dict(filter_result.diagnostics))

        groups = self._build_selection_groups(qualified_items)
        return SelectionResult(
            strategy="keyword",
            qualified_items=qualified_items,
            rejected_items=list(filter_result.rejected_items),
            groups=groups,
            selected_items=list(qualified_items),
            total_candidates=len(snapshot.items),
            total_selected=len(qualified_items),
            diagnostics=diagnostics,
        )

    def filter_items(
        self,
        items: Sequence[HotlistItem],
        *,
        frequency_file: str | None = None,
    ) -> RuleFilterResult:
        """Return items that survive the blacklist gate."""

        rule_set = self._load_rule_set(frequency_file)
        passed_items: list[HotlistItem] = []
        rejected_items: list[SelectionRejectedItem] = []
        global_hit_count = 0
        filter_hit_count = 0

        for item in items:
            title = str(item.title or "")
            title_lower = title.lower()

            global_match = next(
                (token for token in rule_set.global_filters if token.lower() in title_lower),
                "",
            )
            if global_match:
                global_hit_count += 1
                rejected_items.append(
                    self._build_rejection(
                        item,
                        reason=f"matched global blacklist: {global_match}",
                        metadata={"rule_type": "global_filter", "matched_token": global_match},
                    )
                )
                continue

            filter_token = next(
                (token for token in rule_set.filter_tokens if _word_matches(token, title_lower)),
                None,
            )
            if filter_token is not None:
                filter_hit_count += 1
                rejected_items.append(
                    self._build_rejection(
                        item,
                        reason=f"matched filter token: {filter_token.label}",
                        metadata={"rule_type": "filter_token", "matched_token": filter_token.label},
                    )
                )
                continue

            passed_items.append(item)

        return RuleFilterResult(
            passed_items=tuple(passed_items),
            rejected_items=tuple(rejected_items),
            diagnostics={
                "global_filters_count": len(rule_set.global_filters),
                "filter_words_count": len(rule_set.filter_tokens),
                "global_filter_hits": global_hit_count,
                "filter_token_hits": filter_hit_count,
                "rule_group_count": len(rule_set.groups),
                "source_path": rule_set.source_path,
            },
        )

    def _load_rule_set(self, frequency_file: str | None) -> KeywordRuleSet:
        try:
            return load_keyword_rule_set(
                frequency_file,
                config_root=self.config_root,
            )
        except FileNotFoundError:
            if frequency_file:
                raise
            return KeywordRuleSet()

    @staticmethod
    def _build_rejection(
        item: HotlistItem,
        *,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> SelectionRejectedItem:
        return SelectionRejectedItem(
            news_item_id=str(item.news_item_id),
            source_id=item.source_id,
            source_name=item.source_name,
            title=item.title,
            rejected_stage="rule",
            rejected_reason=reason,
            metadata=dict(metadata or {}),
        )

    @staticmethod
    def _build_selection_groups(items: Sequence[HotlistItem]) -> list[SelectionGroup]:
        if not items:
            return []
        return [
            SelectionGroup(
                key="qualified",
                label="精选候选",
                items=list(items),
                position=0,
                metadata={"total_selected": len(items)},
            )
        ]
