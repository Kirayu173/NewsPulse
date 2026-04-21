import os
import unittest
from pathlib import Path

from newspulse.core.loader import load_config
from newspulse.workflow.insight.service import InsightService
from newspulse.workflow.shared.contracts import (
    HotlistItem,
    HotlistSnapshot,
    SelectionGroup,
    SelectionResult,
    StandaloneSection,
)
from newspulse.workflow.shared.options import InsightOptions


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class LiveAIInsightStrategyTest(unittest.TestCase):
    def test_ai_insight_stage_runs_with_real_model(self):
        project_root = Path(__file__).resolve().parents[1]
        _load_dotenv(project_root / ".env")
        if os.environ.get("NEWSPULSE_RUN_LIVE_AI_TESTS") != "1":
            self.skipTest("live AI tests disabled")

        config = load_config(str(project_root / "config" / "config.yaml"))
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
        snapshot = HotlistSnapshot(
            mode="current",
            generated_at="2026-04-17 10:00:00",
            items=[item1, item2],
            standalone_sections=[
                StandaloneSection(key="producthunt", label="Product Hunt", items=[item2]),
            ],
        )
        selection = SelectionResult(
            strategy="ai",
            groups=[SelectionGroup(key="ai", label="AI", items=[item1, item2], position=0)],
            selected_items=[item1, item2],
            total_candidates=2,
            total_selected=2,
        )

        service = InsightService(
            ai_runtime_config=config["AI_ANALYSIS_MODEL"],
            ai_analysis_config=config["AI_ANALYSIS"],
            config_root=project_root / "config",
        )
        result = service.run(
            snapshot,
            selection,
            InsightOptions(
                enabled=True,
                strategy="ai",
                mode="current",
                max_items=2,
            ),
        )

        self.assertTrue(result.enabled)
        self.assertEqual(result.strategy, "ai")
        self.assertGreaterEqual(len(result.sections), 1)
        self.assertTrue(any(section.key == "core_trends" for section in result.sections))
        self.assertTrue(result.raw_response.strip())


if __name__ == "__main__":
    unittest.main()
