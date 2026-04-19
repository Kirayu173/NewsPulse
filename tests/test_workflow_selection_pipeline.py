import unittest

from newspulse.workflow.selection.keyword import RuleFilterResult
from newspulse.workflow.selection.models import AIQualityDecision, SemanticSelectionResult
from newspulse.workflow.selection.pipeline import SelectionPipelineProjector
from newspulse.workflow.shared.contracts import HotlistItem, HotlistSnapshot


class SelectionPipelineProjectorTest(unittest.TestCase):
    def test_projector_rejects_generic_repo_slug_even_if_llm_keeps_it(self):
        specific_repo = HotlistItem(
            news_item_id="1",
            source_id="github-trending-today",
            source_name="GitHub Trending",
            title="browser-use/browser-harness",
            current_rank=1,
            ranks=[1],
        )
        generic_repo = HotlistItem(
            news_item_id="2",
            source_id="github-trending-today",
            source_name="GitHub Trending",
            title="codejunkie99/agentic-stack",
            current_rank=2,
            ranks=[2],
        )
        snapshot = HotlistSnapshot(
            mode="current",
            generated_at="2026-04-19 20:00:00",
            items=[specific_repo, generic_repo],
        )
        projector = SelectionPipelineProjector()

        result = projector.build_selection_result(
            snapshot=snapshot,
            rule_result=RuleFilterResult(
                passed_items=(specific_repo, generic_repo),
                rejected_items=(),
            ),
            semantic_result=SemanticSelectionResult(
                passed_items=(specific_repo, generic_repo),
                rejected_items=(),
            ),
            llm_decisions=[
                AIQualityDecision(
                    news_item_id="1",
                    keep=True,
                    quality_score=0.7,
                    reasons=("clear function",),
                ),
                AIQualityDecision(
                    news_item_id="2",
                    keep=True,
                    quality_score=0.75,
                    reasons=("high-signal keyword",),
                ),
            ],
            llm_min_score=0.65,
        )

        self.assertEqual([item.title for item in result.qualified_items], ["browser-use/browser-harness"])
        self.assertEqual(len(result.rejected_items), 1)
        self.assertEqual(result.rejected_items[0].news_item_id, "2")
        self.assertIn("generic repo slug", result.rejected_items[0].rejected_reason)
        self.assertEqual(result.diagnostics["llm_title_guard_rejected_count"], 1)


if __name__ == "__main__":
    unittest.main()
