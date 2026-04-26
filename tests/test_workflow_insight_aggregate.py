import unittest
from pathlib import Path

from newspulse.workflow.insight.aggregate import InsightAggregateGenerator
from newspulse.workflow.insight.models import (
    InsightNewsContext,
    InsightRankSignals,
    InsightSelectionEvidence,
    InsightSourceContext,
)
from newspulse.workflow.shared.ai_runtime.prompts import PromptTemplate
from newspulse.workflow.shared.contracts import InsightSummary, InsightSummaryBundle
from tests.helpers.runtime import json_result


class StubClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def generate_json(self, messages, **kwargs):
        self.calls.append(messages[-1]["content"])
        return json_result(self.response)


class InsightAggregateGeneratorTest(unittest.TestCase):
    def _contexts(self):
        return [
            InsightNewsContext(
                news_item_id="1",
                title="OpenAI ships a new coding agent",
                source_id="hackernews",
                source_name="Hacker News",
                rank_signals=InsightRankSignals(current_rank=1),
                source_context=InsightSourceContext(source_kind="article", summary="summary"),
                selection_evidence=InsightSelectionEvidence(matched_topics=("AI Agent / MCP",)),
            ),
            InsightNewsContext(
                news_item_id="2",
                title="GitHub launches an open source developer tool",
                source_id="github-trending-today",
                source_name="GitHub Trending",
                rank_signals=InsightRankSignals(current_rank=2),
                source_context=InsightSourceContext(source_kind="github_repository", summary="summary"),
                selection_evidence=InsightSelectionEvidence(matched_topics=("Open Source",)),
            ),
        ]

    def _summary_bundle(self):
        return InsightSummaryBundle(
            item_summaries=[
                InsightSummary(
                    kind="item",
                    key="item:1",
                    title="OpenAI ships a new coding agent",
                    summary="Terminal-native coding workflow stays hot.",
                    item_ids=["1"],
                    evidence_topics=["AI Agent / MCP"],
                    evidence_notes=["workflow angle is clear"],
                    sources=["Hacker News"],
                ),
                InsightSummary(
                    kind="item",
                    key="item:2",
                    title="GitHub launches an open source developer tool",
                    summary="Open source distribution remains a major signal.",
                    item_ids=["2"],
                    evidence_topics=["Open Source"],
                    evidence_notes=["open source momentum"],
                    sources=["GitHub Trending"],
                ),
            ],
            report_summary=InsightSummary(
                kind="report",
                key="report",
                title="报告摘要",
                summary="Two item summaries show developer tooling momentum.",
                item_ids=["1", "2"],
                evidence_topics=["AI Agent / MCP", "Open Source"],
                sources=["Hacker News", "GitHub Trending"],
            ),
        )

    def test_builds_sections_with_supporting_metadata(self):
        client = StubClient(
            {
                "sections": [
                    {
                        "key": "core_trends",
                        "title": "Drifted Title",
                        "content": "Provider-native AI tooling keeps dominating the developer conversation.",
                        "summary": "Provider-native AI tooling stays in focus.",
                        "supporting_news_ids": ["1", "2"],
                        "supporting_topics": ["AI Agent / MCP", "Open Source"],
                        "source_distribution": {"Hacker News": 1, "GitHub Trending": 1},
                    }
                ]
            }
        )
        generator = InsightAggregateGenerator(
            client=client,
            analysis_config={"PROMPT_FILE": "ignored.txt"},
            prompt_template=PromptTemplate(
                path=Path("agg.txt"),
                user_prompt="COUNT={item_summary_count}\n{item_summaries_json}\n{report_summary_json}",
            ),
        )

        sections, raw_response, diagnostics = generator.generate(self._summary_bundle(), self._contexts())

        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0].key, "core_trends")
        self.assertEqual(sections[0].metadata["supporting_news_ids"], ["1", "2"])
        self.assertEqual(diagnostics["section_count"], 1)
        self.assertEqual(diagnostics["item_summary_count"], 2)
        self.assertTrue(raw_response)
        self.assertIn("COUNT=2", client.calls[0])
        self.assertIn("Terminal-native coding workflow stays hot.", client.calls[0])
        self.assertNotIn("theme_summaries_json", client.calls[0])

    def test_supports_dynamic_section_count(self):
        client = StubClient(
            {
                "sections": [
                    {
                        "key": "core_trends",
                        "title": "Whatever",
                        "content": "AI tooling remains a key conversation theme.",
                        "summary": "AI tooling stays central.",
                        "supporting_news_ids": ["1", "2"],
                    },
                    {
                        "key": "signals",
                        "title": "Another Title",
                        "content": "Open source releases continue to reinforce the theme.",
                        "summary": "Open source signals stay strong.",
                        "supporting_news_ids": ["1"],
                    },
                ]
            }
        )
        generator = InsightAggregateGenerator(
            client=client,
            analysis_config={"PROMPT_FILE": "ignored.txt"},
            prompt_template=PromptTemplate(path=Path("agg.txt"), user_prompt="{item_summaries_json}"),
        )

        sections, _, diagnostics = generator.generate(self._summary_bundle(), self._contexts())

        self.assertEqual(diagnostics["section_count"], 2)
        self.assertEqual([section.key for section in sections], ["core_trends", "signals"])

    def test_discards_duplicate_section_keys_from_llm_payload(self):
        client = StubClient(
            {
                "sections": [
                    {
                        "key": "signals",
                        "title": "Signal One",
                        "content": "First signal.",
                        "summary": "First signal summary.",
                        "supporting_news_ids": ["1"],
                    },
                    {
                        "key": "signals",
                        "title": "Signal Two",
                        "content": "Second signal.",
                        "summary": "Second signal summary.",
                        "supporting_news_ids": ["2"],
                    },
                ]
            }
        )
        generator = InsightAggregateGenerator(
            client=client,
            analysis_config={"PROMPT_FILE": "ignored.txt"},
            prompt_template=PromptTemplate(path=Path("agg.txt"), user_prompt="{item_summaries_json}"),
        )

        sections, _, diagnostics = generator.generate(self._summary_bundle(), self._contexts())

        self.assertEqual(diagnostics["section_count"], 1)
        self.assertEqual([section.key for section in sections], ["signals"])
        self.assertEqual(sections[0].content, "First signal.")

    def test_falls_back_from_report_or_item_summaries_only(self):
        class BrokenClient:
            def generate_json(self, messages, **kwargs):
                raise ValueError("not-json")

        generator = InsightAggregateGenerator(
            client=BrokenClient(),
            analysis_config={"PROMPT_FILE": "ignored.txt"},
            prompt_template=PromptTemplate(path=Path("agg.txt"), user_prompt="{item_summaries_json}"),
        )

        bundle = self._summary_bundle()
        bundle.item_summaries = bundle.item_summaries[:1]
        sections, _, diagnostics = generator.generate(bundle, self._contexts()[:1])

        self.assertEqual(sections[0].key, "core_trends")
        self.assertEqual(sections[0].metadata["section_generator"], "aggregate_fallback")
        self.assertIn("Two item summaries", sections[0].content)
        self.assertIn("error", diagnostics)
        self.assertNotIn("theme", sections[0].content.lower())


if __name__ == "__main__":
    unittest.main()
