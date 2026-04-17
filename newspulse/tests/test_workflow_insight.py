import json
import unittest
from pathlib import Path

from newspulse.workflow.insight.ai import AIInsightStrategy
from newspulse.workflow.insight.service import InsightService
from newspulse.workflow.shared.ai_runtime.prompts import PromptTemplate
from newspulse.workflow.shared.contracts import (
    HotlistItem,
    HotlistSnapshot,
    InsightResult,
    SelectionGroup,
    SelectionResult,
    StandaloneSection,
)
from newspulse.workflow.shared.options import InsightOptions


def _build_snapshot_and_selection():
    item1 = HotlistItem(
        news_item_id="1",
        source_id="hackernews",
        source_name="Hacker News",
        title="OpenAI launches a new coding agent",
        current_rank=1,
        ranks=[1, 2],
        first_time="2026-04-17 09:00:00",
        last_time="2026-04-17 10:00:00",
        count=2,
        rank_timeline=[{"time": "09:00", "rank": 2}, {"time": "10:00", "rank": 1}],
        is_new=True,
    )
    item2 = HotlistItem(
        news_item_id="2",
        source_id="github-trending-today",
        source_name="GitHub Trending",
        title="GitHub ships a new open source CLI",
        current_rank=2,
        ranks=[2],
        first_time="2026-04-17 10:00:00",
        last_time="2026-04-17 10:00:00",
        count=1,
    )
    item3 = HotlistItem(
        news_item_id="3",
        source_id="producthunt",
        source_name="Product Hunt",
        title="Startup launches AI productivity app",
        current_rank=3,
        ranks=[3],
        first_time="2026-04-17 10:00:00",
        last_time="2026-04-17 10:00:00",
        count=1,
    )

    snapshot = HotlistSnapshot(
        mode="current",
        generated_at="2026-04-17 10:00:00",
        items=[item1, item2, item3],
        standalone_sections=[
            StandaloneSection(
                key="wallstreetcn-hot",
                label="华尔街见闻",
                items=[item3],
            )
        ],
    )
    selection = SelectionResult(
        strategy="keyword",
        groups=[
            SelectionGroup(key="ai", label="AI", items=[item1, item3], position=0),
            SelectionGroup(key="oss", label="OpenSource", items=[item2], position=1),
        ],
        selected_items=[item1, item2, item3],
        total_candidates=3,
        total_selected=3,
    )
    return snapshot, selection


class FakeInsightClient:
    def __init__(self):
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append(messages[-1]["content"])
        return json.dumps(
            {
                "core_trends": "AI agent launches and developer tools dominate attention.",
                "sentiment_controversy": "Excitement is high, but there is caution about product durability.",
                "signals": "OpenAI, GitHub and startup launches keep appearing together.",
                "outlook_strategy": "Keep tracking product launches and tool adoption across platforms.",
                "standalone_summaries": {
                    "华尔街见闻": "The standalone section highlights follow-up startup coverage."
                },
            }
        )


class WorkflowInsightServiceTest(unittest.TestCase):
    def test_noop_strategy_returns_empty_insight_result(self):
        snapshot, selection = _build_snapshot_and_selection()
        service = InsightService()

        result = service.run(
            snapshot,
            selection,
            InsightOptions(enabled=False, strategy="ai"),
        )

        self.assertIsInstance(result, InsightResult)
        self.assertFalse(result.enabled)
        self.assertEqual(result.strategy, "noop")
        self.assertEqual(result.sections, [])
        self.assertTrue(result.diagnostics["skipped"])

    def test_ai_strategy_builds_structured_sections_from_model_response(self):
        snapshot, selection = _build_snapshot_and_selection()
        client = FakeInsightClient()
        prompt_template = PromptTemplate(
            path=Path("test-prompt.txt"),
            user_prompt=(
                "MODE={report_mode}\n"
                "TYPE={report_type}\n"
                "COUNT={news_count}\n"
                "PLATFORMS={platforms}\n"
                "KEYWORDS={keywords}\n"
                "NEWS:\n{news_content}\n"
                "STANDALONE:\n{standalone_content}\n"
                "LANG={language}"
            ),
        )
        strategy = AIInsightStrategy(
            client=client,
            analysis_config={"LANGUAGE": "Chinese"},
            prompt_template=prompt_template,
        )
        service = InsightService(ai_strategy=strategy)

        result = service.run(
            snapshot,
            selection,
            InsightOptions(
                enabled=True,
                strategy="ai",
                mode="current",
                max_items=2,
                include_standalone=True,
                include_rank_timeline=True,
            ),
        )

        self.assertTrue(result.enabled)
        self.assertEqual(result.strategy, "ai")
        self.assertEqual(
            [section.key for section in result.sections[:4]],
            ["core_trends", "sentiment_controversy", "signals", "outlook_strategy"],
        )
        self.assertEqual(result.sections[4].key, "standalone:华尔街见闻")
        self.assertEqual(result.diagnostics["analyzed_items"], 2)
        self.assertTrue(result.diagnostics["standalone_included"])
        self.assertEqual(len(client.calls), 1)
        prompt = client.calls[0]
        self.assertIn("OpenAI launches a new coding agent", prompt)
        self.assertIn("GitHub ships a new open source CLI", prompt)
        self.assertIn("Startup launches AI productivity app", prompt)
        self.assertIn("轨迹:2(09:00) -> 1(10:00)", prompt)
        self.assertIn("华尔街见闻", prompt)

    def test_service_raises_for_unknown_strategy(self):
        snapshot, selection = _build_snapshot_and_selection()
        service = InsightService()

        with self.assertRaises(NotImplementedError):
            service.run(snapshot, selection, InsightOptions(enabled=True, strategy="custom"))


if __name__ == "__main__":
    unittest.main()
