import os
import unittest
from pathlib import Path

from newspulse.core.loader import load_config
from newspulse.runtime import build_runtime, run_insight_stage
from newspulse.workflow.shared.contracts import (
    HotlistItem,
    HotlistSnapshot,
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


class LiveRuntimeInsightStageTest(unittest.TestCase):
    def test_run_insight_stage_uses_real_model(self):
        project_root = Path(__file__).resolve().parents[1]
        _load_dotenv(project_root / ".env")
        if os.environ.get("NEWSPULSE_RUN_LIVE_AI_TESTS") != "1":
            self.skipTest("live AI tests disabled")

        config = load_config(str(project_root / "config" / "config.yaml"))
        config["AI_ANALYSIS"]["ENABLED"] = True
        config["AI_ANALYSIS"]["MODE"] = "current"
        config["AI_ANALYSIS"]["MAX_ITEMS"] = 2
        runtime = build_runtime(config)

        snapshot = HotlistSnapshot(
            mode="current",
            generated_at="2026-04-17 10:00:00",
            items=[
                HotlistItem(
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
                ),
                HotlistItem(
                    news_item_id="2",
                    source_id="github-trending-today",
                    source_name="GitHub Trending",
                    title="GitHub ships a new open source CLI",
                    current_rank=2,
                    ranks=[2],
                    first_time="2026-04-17 10:00:00",
                    last_time="2026-04-17 10:00:00",
                    count=1,
                ),
            ],
            standalone_sections=[
                StandaloneSection(
                    key="producthunt",
                    label="Product Hunt",
                    items=[
                        HotlistItem(
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
                    ],
                )
            ],
        )
        selection = SelectionResult(
            strategy="keyword",
            groups=[SelectionGroup(key="ai", label="AI", items=list(snapshot.items), position=0)],
            selected_items=list(snapshot.items),
            total_candidates=2,
            total_selected=2,
        )

        try:
            insight = run_insight_stage(
                runtime.settings,
                runtime.container,
                runtime.selection_builder,
                runtime.insight_builder,
                report_mode="current",
                snapshot=snapshot,
                selection=selection,
                strategy="keyword",
            )

            self.assertTrue(insight.enabled)
            self.assertEqual(insight.strategy, "ai")
            self.assertEqual(insight.diagnostics["report_mode"], "current")
            self.assertTrue(insight.raw_response.strip())
            self.assertTrue(any(section.content for section in insight.sections))
        finally:
            runtime.cleanup()


if __name__ == "__main__":
    unittest.main()
