# coding=utf-8
"""Projection helpers for the single-line selection funnel."""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from newspulse.workflow.selection.keyword import RuleFilterResult
from newspulse.workflow.selection.models import AIQualityDecision, SemanticSelectionResult
from newspulse.workflow.shared.contracts import (
    HotlistItem,
    SelectionGroup,
    SelectionRejectedItem,
    SelectionResult,
)


class SelectionPipelineProjector:
    """Project funnel stage outputs into the native SelectionResult contract."""

    def build_selection_result(
        self,
        *,
        snapshot: Any,
        rule_result: RuleFilterResult,
        semantic_result: SemanticSelectionResult,
        llm_decisions: Sequence[AIQualityDecision],
        llm_min_score: float,
    ) -> SelectionResult:
        snapshot_items = {str(item.news_item_id): item for item in snapshot.items}
        decision_map = {decision.news_item_id: decision for decision in llm_decisions}
        semantic_kept_ids = {str(item.news_item_id) for item in semantic_result.passed_items}
        missing_decision_count = max(0, len(semantic_kept_ids) - len(decision_map))
        title_guard_rejected_count = 0

        qualified_items: list[HotlistItem] = []
        rejected_items: list[SelectionRejectedItem] = []
        final_matches: list[dict[str, Any]] = []

        rejected_items.extend(rule_result.rejected_items)
        rejected_items.extend(semantic_result.rejected_items)

        for item in semantic_result.passed_items:
            item_id = str(item.news_item_id)
            decision = decision_map.get(item_id)
            if decision is None:
                rejected_items.append(
                    SelectionRejectedItem(
                        news_item_id=item_id,
                        source_id=item.source_id,
                        source_name=item.source_name,
                        title=item.title,
                        rejected_stage="llm",
                        rejected_reason="llm did not return a decision",
                        metadata={"min_quality_score": llm_min_score},
                    )
                )
                continue

            if not decision.keep or decision.quality_score < llm_min_score:
                rejected_items.append(
                    SelectionRejectedItem(
                        news_item_id=item_id,
                        source_id=item.source_id,
                        source_name=item.source_name,
                        title=item.title,
                        rejected_stage="llm",
                        rejected_reason=_build_llm_rejection_reason(decision, llm_min_score),
                        score=decision.quality_score,
                        metadata={
                            "reasons": list(decision.reasons),
                            "evidence": decision.evidence,
                            "matched_topics": list(decision.matched_topics),
                        },
                    )
                )
                continue

            guard_reason = _build_title_quality_guard_reason(item)
            if guard_reason:
                title_guard_rejected_count += 1
                rejected_items.append(
                    SelectionRejectedItem(
                        news_item_id=item_id,
                        source_id=item.source_id,
                        source_name=item.source_name,
                        title=item.title,
                        rejected_stage="llm",
                        rejected_reason=guard_reason,
                        score=decision.quality_score,
                        metadata={
                            "quality_guard": "title_specificity",
                            "reasons": list(decision.reasons),
                            "evidence": decision.evidence,
                            "matched_topics": list(decision.matched_topics),
                        },
                    )
                )
                continue

            qualified_items.append(item)
            final_matches.append(
                {
                    "news_item_id": item_id,
                    "source_id": item.source_id,
                    "source_name": item.source_name,
                    "title": item.title,
                    "current_rank": item.current_rank,
                    "quality_score": round(decision.quality_score, 6),
                    "decision_layer": "llm_quality_gate",
                    "reasons": list(decision.reasons),
                    "matched_topics": list(decision.matched_topics),
                    "evidence": decision.evidence,
                }
            )

        # Defensive catch-all for disabled semantic stage that passes everything through.
        if not semantic_kept_ids and rule_result.passed_items and semantic_result.diagnostics.get("skipped"):
            for item in rule_result.passed_items:
                if str(item.news_item_id) not in decision_map:
                    continue

        qualified_items.sort(key=lambda item: ((item.current_rank or 9999), item.title.lower()))
        rejected_items = _dedupe_rejections(rejected_items, snapshot_items)
        groups = self._build_selection_groups(qualified_items)

        return SelectionResult(
            strategy="ai",
            qualified_items=qualified_items,
            rejected_items=rejected_items,
            groups=groups,
            selected_items=list(qualified_items),
            total_candidates=len(snapshot.items),
            total_selected=len(qualified_items),
            diagnostics={
                "qualified_count": len(qualified_items),
                "rejected_count": len(rejected_items),
                "rule_rejected_count": len(rule_result.rejected_items),
                "semantic_rejected_count": len(semantic_result.rejected_items),
                "llm_evaluated_count": len(llm_decisions),
                "llm_missing_decision_count": missing_decision_count,
                "llm_title_guard_rejected_count": title_guard_rejected_count,
                "selected_matches": final_matches,
            },
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


def _build_llm_rejection_reason(decision: AIQualityDecision, min_score: float) -> str:
    if not decision.keep:
        if decision.reasons:
            return "; ".join(decision.reasons)
        return "llm rejected the item"
    return f"quality score below threshold {min_score:.2f}"


_GENERIC_REPO_TITLE_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_GENERIC_REPO_TOKENS = frozenset(
    {
        "agent",
        "agentic",
        "agents",
        "ai",
        "app",
        "assistant",
        "awesome",
        "copilot",
        "kit",
        "lab",
        "llm",
        "rag",
        "skill",
        "skills",
        "stack",
        "starter",
        "starterkit",
        "studio",
        "tool",
        "toolkit",
        "workflow",
        "workflows",
    }
)
_CONCRETE_REPO_TOKENS = frozenset(
    {
        "benchmark",
        "browser",
        "cli",
        "code",
        "compiler",
        "dataset",
        "diffusion",
        "editor",
        "embedding",
        "engine",
        "gateway",
        "harness",
        "index",
        "inference",
        "kernel",
        "mcp",
        "model",
        "monitor",
        "router",
        "runtime",
        "sdk",
        "search",
        "server",
        "terminal",
        "ui",
        "vision",
    }
)


def _build_title_quality_guard_reason(item: HotlistItem) -> str:
    if _is_generic_repo_slug_title(item):
        return "generic repo slug lacks a concrete function signal"
    return ""


def _is_generic_repo_slug_title(item: HotlistItem) -> bool:
    if str(item.source_id or "").strip() != "github-trending-today":
        return False

    title = str(item.title or "").strip()
    if not _GENERIC_REPO_TITLE_PATTERN.fullmatch(title):
        return False

    _, repo_name = title.split("/", 1)
    tokens = [token for token in re.split(r"[-_.]+", repo_name.lower()) if token]
    if not tokens:
        return False
    if any(token in _CONCRETE_REPO_TOKENS for token in tokens):
        return False

    generic_hits = sum(1 for token in tokens if token in _GENERIC_REPO_TOKENS)
    return generic_hits > 0 and generic_hits == len(tokens)


def _dedupe_rejections(
    rejected_items: Sequence[SelectionRejectedItem],
    snapshot_items: Mapping[str, HotlistItem],
) -> list[SelectionRejectedItem]:
    best_by_id: dict[str, SelectionRejectedItem] = {}
    stage_priority = {"rule": 0, "semantic": 1, "llm": 2}
    for rejected in rejected_items:
        item_id = str(rejected.news_item_id)
        existing = best_by_id.get(item_id)
        if existing is None:
            best_by_id[item_id] = rejected
            continue
        current_priority = stage_priority.get(existing.rejected_stage, 99)
        next_priority = stage_priority.get(rejected.rejected_stage, 99)
        if next_priority < current_priority:
            best_by_id[item_id] = rejected

    return [
        best_by_id[item_id]
        for item_id in sorted(
            best_by_id,
            key=lambda value: (
                snapshot_items.get(value).current_rank if snapshot_items.get(value) is not None else 9999,
                snapshot_items.get(value).title.lower() if snapshot_items.get(value) is not None else value,
            ),
        )
    ]
