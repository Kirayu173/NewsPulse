import os
import unittest
from pathlib import Path

from newspulse.context import AppContext
from newspulse.core.loader import load_config
from newspulse.workflow.shared.contracts import (
    HotlistItem,
    InsightResult,
    InsightSection,
    RenderableReport,
    SelectionGroup,
    SelectionResult,
    StandaloneSection,
)


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class LiveWorkflowLocalizationStageTest(unittest.TestCase):
    def test_localization_stage_runs_with_real_model(self):
        project_root = Path(__file__).resolve().parents[2]
        _load_dotenv(project_root / ".env")
        if os.environ.get("NEWSPULSE_RUN_LIVE_AI_TESTS") != "1":
            self.skipTest("live AI tests disabled")

        config = load_config(str(project_root / "newspulse" / "config" / "config.yaml"))
        config["AI_TRANSLATION"]["ENABLED"] = True
        config["AI_TRANSLATION"]["LANGUAGE"] = "Chinese"
        config["AI_TRANSLATION"]["SCOPE"]["HOTLIST"] = True
        config["AI_TRANSLATION"]["SCOPE"]["STANDALONE"] = True
        config["AI_TRANSLATION"]["SCOPE"]["INSIGHT"] = True
        ctx = AppContext(config)

        item1 = HotlistItem(
            news_item_id="1",
            source_id="hackernews",
            source_name="Hacker News",
            title="OpenAI launches a new coding agent",
            current_rank=1,
            ranks=[1, 2],
        )
        item2 = HotlistItem(
            news_item_id="2",
            source_id="producthunt",
            source_name="Product Hunt",
            title="Startup launches AI productivity app",
            current_rank=2,
            ranks=[2],
        )
        report = RenderableReport(
            meta={"mode": "current", "report_type": "实时报告"},
            selection=SelectionResult(
                strategy="keyword",
                groups=[SelectionGroup(key="ai", label="AI", items=[item1, item2], position=0)],
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
                        title="Core Trends",
                        content="AI coding tools and startup launches keep dominating the conversation.",
                    )
                ],
            ),
            new_items=[item1],
            standalone_sections=[StandaloneSection(key="producthunt", label="Product Hunt", items=[item2])],
            display_regions=["hotlist", "new_items", "standalone", "insight"],
        )

        localized = ctx.run_localization_stage(report)

        self.assertEqual(localized.language, "Chinese")
        self.assertIn("1", localized.localized_titles)
        self.assertIn("2", localized.localized_titles)
        self.assertIn("core_trends", localized.localized_sections)
        self.assertTrue(localized.translation_meta["title_raw_response"].strip())
        self.assertTrue(localized.translation_meta["section_raw_response"].strip())


if __name__ == "__main__":
    unittest.main()
