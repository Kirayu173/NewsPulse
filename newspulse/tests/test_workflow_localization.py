import unittest
from pathlib import Path

from newspulse.context import AppContext
from newspulse.workflow.localization import LocalizationService
from newspulse.workflow.localization.ai import AILocalizationStrategy
from newspulse.workflow.shared.ai_runtime.prompts import PromptTemplate
from newspulse.workflow.shared.contracts import (
    HotlistItem,
    InsightResult,
    InsightSection,
    RenderableReport,
    SelectionGroup,
    SelectionResult,
    StandaloneSection,
)
from newspulse.workflow.shared.options import LocalizationOptions, LocalizationScope


def _build_renderable_report() -> RenderableReport:
    item1 = HotlistItem(
        news_item_id="1",
        source_id="hackernews",
        source_name="Hacker News",
        title="OpenAI launches a new coding agent",
        current_rank=1,
        ranks=[1],
    )
    item2 = HotlistItem(
        news_item_id="2",
        source_id="producthunt",
        source_name="Product Hunt",
        title="Startup launches AI productivity app",
        current_rank=2,
        ranks=[2],
    )
    return RenderableReport(
        meta={
            "mode": "current",
            "report_type": "实时报告",
            "timezone": "Asia/Hong_Kong",
        },
        selection=SelectionResult(
            strategy="keyword",
            groups=[
                SelectionGroup(key="ai", label="AI", items=[item1, item2], position=0),
                SelectionGroup(key="dup", label="Dup", items=[item1], position=1),
            ],
            selected_items=[item1, item2],
            total_candidates=2,
            total_selected=2,
        ),
        insight=InsightResult(
            enabled=True,
            strategy="ai",
            sections=[
                InsightSection(
                    key="core_trends",
                    title="核心趋势",
                    content="AI tools keep dominating the developer conversation.",
                )
            ],
        ),
        new_items=[item1],
        standalone_sections=[StandaloneSection(key="producthunt", label="Product Hunt", items=[item2])],
        display_regions=["hotlist", "new_items", "standalone", "insight"],
    )


def _build_prompt_template() -> PromptTemplate:
    return PromptTemplate(
        path=Path("localization-prompt.txt"),
        user_prompt="LANG={target_language}\n{content}",
    )


class RecordingLocalizationClient:
    def __init__(self, *, drop_last_item: bool = False):
        self.calls: list[list[str]] = []
        self.drop_last_item = drop_last_item

    def chat(self, messages, **kwargs):
        texts: list[str] = []
        for line in messages[-1]["content"].splitlines():
            stripped = line.strip()
            if not stripped.startswith("[") or "]" not in stripped:
                continue
            texts.append(stripped[stripped.index("]") + 1 :].strip())

        self.calls.append(texts)
        if self.drop_last_item and texts:
            texts = texts[:-1]

        return "\n".join(
            f"[{index}] ZH:{text}"
            for index, text in enumerate(texts, start=1)
        )


class WorkflowLocalizationStageTest(unittest.TestCase):
    def test_ai_localization_strategy_translates_titles_and_sections_with_dedup(self):
        report = _build_renderable_report()
        client = RecordingLocalizationClient()
        service = LocalizationService(
            ai_strategy=AILocalizationStrategy(
                client=client,
                prompt_template=_build_prompt_template(),
            ),
        )

        localized = service.run(
            report,
            LocalizationOptions(
                enabled=True,
                strategy="ai",
                language="Chinese",
                scope=LocalizationScope(
                    selection_titles=True,
                    new_items=True,
                    standalone=True,
                    insight_sections=True,
                ),
            ),
        )

        self.assertEqual(localized.language, "Chinese")
        self.assertEqual(localized.localized_titles["1"], "ZH:OpenAI launches a new coding agent")
        self.assertEqual(localized.localized_titles["2"], "ZH:Startup launches AI productivity app")
        self.assertEqual(
            localized.localized_sections["core_trends"],
            "ZH:AI tools keep dominating the developer conversation.",
        )
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(len(client.calls[0]), 2)
        self.assertIn("OpenAI launches a new coding agent", client.calls[0])
        self.assertIn("AI tools keep dominating the developer conversation.", client.calls[1])
        self.assertEqual(localized.translation_meta["title_success_count"], 2)
        self.assertEqual(localized.translation_meta["section_success_count"], 1)
        self.assertIn("LANG=Chinese", localized.translation_meta["title_prompt"])

    def test_ai_localization_strategy_records_partial_batch_parse_failures(self):
        report = _build_renderable_report()
        client = RecordingLocalizationClient(drop_last_item=True)
        strategy = AILocalizationStrategy(
            client=client,
            prompt_template=_build_prompt_template(),
        )

        localized = strategy.run(
            report,
            LocalizationOptions(
                enabled=True,
                strategy="ai",
                language="Chinese",
                scope=LocalizationScope(
                    selection_titles=True,
                    new_items=True,
                    standalone=True,
                    insight_sections=False,
                ),
            ),
        )

        self.assertEqual(localized.localized_titles["1"], "ZH:OpenAI launches a new coding agent")
        self.assertNotIn("2", localized.localized_titles)
        self.assertEqual(localized.translation_meta["title_success_count"], 1)
        self.assertEqual(localized.translation_meta["title_fail_count"], 1)
        self.assertIn("translation result is empty", localized.translation_meta["errors"])

    def test_context_localization_options_map_legacy_translation_scope(self):
        ctx = AppContext(
            {
                "AI_TRANSLATION": {
                    "ENABLED": True,
                    "LANGUAGE": "Japanese",
                    "SCOPE": {
                        "HOTLIST": False,
                        "STANDALONE": True,
                        "INSIGHT": True,
                    },
                }
            }
        )

        options = ctx.build_localization_options()

        self.assertTrue(options.enabled)
        self.assertEqual(options.strategy, "ai")
        self.assertEqual(options.language, "Japanese")
        self.assertFalse(options.scope.selection_titles)
        self.assertFalse(options.scope.new_items)
        self.assertTrue(options.scope.standalone)
        self.assertTrue(options.scope.insight_sections)

    def test_context_run_localization_stage_uses_renderable_report_input(self):
        report = _build_renderable_report()
        client = RecordingLocalizationClient()
        ctx = AppContext(
            {
                "AI_TRANSLATION": {
                    "ENABLED": True,
                    "LANGUAGE": "Chinese",
                    "SCOPE": {
                        "HOTLIST": True,
                        "STANDALONE": True,
                        "INSIGHT": False,
                    },
                },
                "AI_TRANSLATION_MODEL": {
                    "MODEL": "openai/translation",
                    "API_KEY": "test-key",
                },
            }
        )
        service = LocalizationService(
            ai_strategy=AILocalizationStrategy(
                client=client,
                prompt_template=_build_prompt_template(),
            )
        )

        localized = ctx.run_localization_stage(report, localization_service=service)

        self.assertEqual(localized.localized_titles["1"], "ZH:OpenAI launches a new coding agent")
        self.assertNotIn("core_trends", localized.localized_sections)
        self.assertEqual(len(client.calls), 1)


if __name__ == "__main__":
    unittest.main()
