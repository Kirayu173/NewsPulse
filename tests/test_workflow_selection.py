import unittest
from pathlib import Path
from uuid import uuid4

from newspulse.workflow.report import ReportPackageAssembler
from newspulse.workflow import build_render_view_model
from newspulse.workflow.render import render_hotlist_stats_html
from newspulse.workflow.selection.service import SelectionService
from newspulse.workflow.shared.contracts import HotlistItem, HotlistSnapshot, InsightResult
from newspulse.workflow.shared.options import SelectionOptions
from tests.helpers.io import write_text

TEST_TMPDIR = Path("tmp_test_work")
TEST_TMPDIR.mkdir(exist_ok=True)


def _make_tmp_dir() -> Path:
    path = TEST_TMPDIR / f"case-{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


class SelectionServiceTest(unittest.TestCase):
    def test_keyword_selection_filters_blacklisted_items_and_keeps_remaining_candidates(self):
        tmp_root = _make_tmp_dir()
        config_root = tmp_root / "config"
        write_text(
            config_root / "custom" / "keyword" / "selection.txt",
            """
            [GLOBAL_FILTER]
            Ignore

            [WORD_GROUPS]
            !rumor
            """,
        )

        snapshot = HotlistSnapshot(
            mode="current",
            generated_at="2026-04-17 10:00:00",
            items=[
                HotlistItem(news_item_id="1", source_id="s1", source_name="Platform 1", title="AI launches new model", current_rank=1),
                HotlistItem(news_item_id="2", source_id="s1", source_name="Platform 1", title="Ignore this AI rumor", current_rank=2),
                HotlistItem(news_item_id="3", source_id="s2", source_name="Platform 2", title="Open source database release", current_rank=3),
            ],
        )

        service = SelectionService(config_root=str(config_root))
        result = service.run(
            snapshot,
            SelectionOptions(strategy="keyword", frequency_file="selection.txt"),
        )

        self.assertEqual(result.strategy, "keyword")
        self.assertEqual(result.total_candidates, 3)
        self.assertEqual(result.total_selected, 2)
        self.assertEqual(
            [item.title for item in result.qualified_items],
            ["AI launches new model", "Open source database release"],
        )
        self.assertEqual(len(result.rejected_items), 1)
        self.assertEqual(result.rejected_items[0].rejected_stage, "rule")
        self.assertIn("global blacklist", result.rejected_items[0].rejected_reason)
        self.assertEqual(result.diagnostics["blacklist_rejected_count"], 1)

    def test_keyword_selection_result_feeds_render_with_report_package(self):
        tmp_root = _make_tmp_dir()
        config_root = tmp_root / "config"
        write_text(
            config_root / "custom" / "keyword" / "render.txt",
            """
            [GLOBAL_FILTER]
            Ignore
            """,
        )

        snapshot = HotlistSnapshot(
            mode="current",
            generated_at="2026-04-17 10:00:00",
            items=[
                HotlistItem(
                    news_item_id="1",
                    source_id="s1",
                    source_name="Platform 1",
                    title="AI launches new model",
                    url="https://example.com/a",
                    mobile_url="https://m.example.com/a",
                    ranks=[2, 1],
                    current_rank=1,
                    first_time="09:00",
                    last_time="10:00",
                    count=3,
                    is_new=True,
                ),
                HotlistItem(
                    news_item_id="2",
                    source_id="s2",
                    source_name="Platform 2",
                    title="Ignore this rumor",
                    current_rank=2,
                ),
            ],
        )

        service = SelectionService(config_root=str(config_root))
        result = service.run(snapshot, SelectionOptions(strategy="keyword", frequency_file="render.txt"))
        result.groups = []
        package = ReportPackageAssembler(
            timezone="Asia/Hong_Kong",
            display_mode="keyword",
        ).assemble(
            snapshot,
            result,
            InsightResult(enabled=False, strategy="noop", diagnostics={"reason": "disabled"}),
        )
        view_model = build_render_view_model(package, display_mode="keyword", rank_threshold=5)
        html = render_hotlist_stats_html(view_model.hotlist_groups, display_mode=view_model.display_mode)

        self.assertEqual([group.label for group in view_model.hotlist_groups], ["Platform 1"])
        self.assertEqual(view_model.hotlist_groups[0].items[0].title, "AI launches new model")
        self.assertIn("Platform 1", html)
        self.assertIn("news-item new", html)
        self.assertIn("09:00~10:00", html)


if __name__ == "__main__":
    unittest.main()
