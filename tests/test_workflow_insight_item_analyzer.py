import unittest
from pathlib import Path

from newspulse.workflow.insight.item_analyzer import InsightItemAnalyzer
from newspulse.workflow.insight.models import (
    InsightNewsContext,
    InsightRankSignals,
    InsightSelectionEvidence,
    InsightSourceContext,
    ReducedContentBundle,
)
from newspulse.workflow.shared.ai_runtime.prompts import PromptTemplate
from tests.helpers.runtime import json_result


class QueueClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def generate_json(self, messages, **kwargs):
        self.calls.append(messages[-1]["content"])
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return json_result(response)


class InsightItemAnalyzerTest(unittest.TestCase):
    def _context(self, news_item_id="1", title="OpenAI ships a new coding agent"):
        return InsightNewsContext(
            news_item_id=news_item_id,
            title=title,
            source_id="hackernews",
            source_name="Hacker News",
            rank_signals=InsightRankSignals(current_rank=1, best_rank=1, worst_rank=2, appearance_count=2, rank_trend="up"),
            source_context=InsightSourceContext(
                source_kind="article",
                summary="The release focuses on developer automation and agent workflows.",
                attributes=("host: example.com",),
            ),
            selection_evidence=InsightSelectionEvidence(
                matched_topics=("AI Agent / MCP",),
                quality_score=0.95,
                semantic_score=0.8,
                llm_reasons=("high-signal release",),
            ),
        )

    def _bundle(self, news_item_id="1"):
        return ReducedContentBundle(
            news_item_id=news_item_id,
            status="ok",
            anchor_text="OpenAI launches a coding agent",
            reduced_text="OpenAI introduced a new coding agent focused on developer workflows.",
            evidence_sentences=("The launch focuses on developer automation.",),
        )

    def test_parses_structured_json_output(self):
        client = QueueClient(
            [
                {
                    "what_happened": "OpenAI launched a coding agent for developer workflows.",
                    "key_facts": ["The product targets agentic coding", "It focuses on developer automation"],
                    "why_it_matters": "It raises the bar for provider-native coding assistants.",
                    "watchpoints": ["Pricing and tool support remain unclear"],
                    "uncertainties": ["The rollout scope is still limited"],
                    "evidence": ["The launch focuses on developer automation."],
                    "confidence": 0.86,
                }
            ]
        )
        analyzer = InsightItemAnalyzer(
            client=client,
            analysis_config={"ITEM_PROMPT_FILE": "ignored.txt"},
            prompt_template=PromptTemplate(path=Path("item.txt"), user_prompt="TITLE={title}\nCONTENT={reduced_content}"),
        )

        analysis = analyzer.analyze_one(self._context(), self._bundle())

        self.assertEqual(analysis.diagnostics["status"], "ok")
        self.assertIn("provider-native coding assistants", analysis.why_it_matters)
        self.assertEqual(analysis.confidence, 0.86)
        self.assertEqual(len(client.calls), 1)
        self.assertIn("CONTENT=", client.calls[0])

    def test_isolates_single_item_failure(self):
        client = QueueClient(
            [
                {
                    "what_happened": "ok",
                    "key_facts": ["a"],
                    "why_it_matters": "b",
                    "watchpoints": [],
                    "uncertainties": [],
                    "evidence": ["e"],
                    "confidence": 0.7,
                },
                RuntimeError("boom"),
            ]
        )
        analyzer = InsightItemAnalyzer(
            client=client,
            analysis_config={"ITEM_PROMPT_FILE": "ignored.txt"},
            prompt_template=PromptTemplate(path=Path("item.txt"), user_prompt="TITLE={title}\nCONTENT={reduced_content}"),
        )

        results = analyzer.analyze_many(
            [self._context("1", "A"), self._context("2", "B")],
            [self._bundle("1"), self._bundle("2")],
        )

        self.assertEqual(results[0].diagnostics["status"], "ok")
        self.assertEqual(results[1].diagnostics["status"], "error")
        self.assertIn("boom", results[1].diagnostics["error"])


if __name__ == "__main__":
    unittest.main()
