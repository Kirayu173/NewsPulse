import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from newspulse.workflow.render import render_hotlist_stats_html
from newspulse.workflow import build_render_view_model
from newspulse.workflow.selection.service import SelectionService
from newspulse.workflow.shared.contracts import HotlistItem, HotlistSnapshot, InsightResult, LocalizedReport, RenderableReport
from newspulse.workflow.shared.options import SelectionOptions


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip(), encoding="utf-8")


class SelectionServiceTest(unittest.TestCase):
    def test_keyword_selection_groups_items_and_applies_caps(self):
        with TemporaryDirectory() as tmp:
            config_root = Path(tmp) / "config"
            _write_text(
                config_root / "custom" / "keyword" / "selection.txt",
                """
                [WORD_GROUPS]
                [AI]
                AI
                @1

                [OpenSource]
                Open

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
                        ranks=[2, 1],
                        current_rank=1,
                        first_time="2026-04-17 09:00:00",
                        last_time="2026-04-17 10:00:00",
                        count=3,
                        is_new=True,
                    ),
                    HotlistItem(
                        news_item_id="2",
                        source_id="s1",
                        source_name="Platform 1",
                        title="AI startup raises funding",
                        url="https://example.com/b",
                        ranks=[5],
                        current_rank=5,
                        first_time="2026-04-17 10:00:00",
                        last_time="2026-04-17 10:00:00",
                        count=1,
                    ),
                    HotlistItem(
                        news_item_id="3",
                        source_id="s2",
                        source_name="Platform 2",
                        title="Open source database release",
                        url="https://example.com/c",
                        ranks=[3],
                        current_rank=3,
                        first_time="2026-04-17 10:00:00",
                        last_time="2026-04-17 10:00:00",
                        count=2,
                    ),
                    HotlistItem(
                        news_item_id="4",
                        source_id="s2",
                        source_name="Platform 2",
                        title="Ignore this AI rumor",
                        url="https://example.com/d",
                        ranks=[1],
                        current_rank=1,
                        first_time="2026-04-17 10:00:00",
                        last_time="2026-04-17 10:00:00",
                        count=1,
                    ),
                ],
            )

            service = SelectionService(
                config_root=str(config_root),
                rank_threshold=5,
                weight_config={
                    "RANK_WEIGHT": 0.6,
                    "FREQUENCY_WEIGHT": 0.3,
                    "HOTNESS_WEIGHT": 0.1,
                },
                max_news_per_keyword=0,
                sort_by_position_first=False,
            )
            result = service.run(
                snapshot,
                SelectionOptions(strategy="keyword", frequency_file="selection.txt"),
            )

            self.assertEqual(result.strategy, "keyword")
            self.assertEqual(result.total_candidates, 4)
            self.assertEqual(result.total_selected, 2)
            self.assertEqual([group.label for group in result.groups], ["AI", "OpenSource"])
            self.assertEqual([item.title for item in result.groups[0].items], ["AI launches new model"])
            self.assertEqual([item.title for item in result.groups[1].items], ["Open source database release"])
            self.assertEqual([item.news_item_id for item in result.selected_items], ["1", "3"])
            self.assertEqual(result.diagnostics["matched_candidates"], 3)

            view_model = build_render_view_model(
                LocalizedReport(
                    base_report=RenderableReport(
                        meta={"mode": "current", "report_type": "实时报告"},
                        selection=result,
                        insight=InsightResult(),
                        display_regions=["hotlist"],
                    )
                ),
                display_mode="keyword",
                rank_threshold=5,
            )
            self.assertEqual([group.label for group in view_model.hotlist_groups], ["AI", "OpenSource"])
            self.assertEqual(view_model.hotlist_groups[0].count, 2)
            self.assertTrue(view_model.hotlist_groups[0].items[0].is_new)
            self.assertEqual(
                view_model.hotlist_groups[0].items[0].time_display,
                "[2026-04-17 09:00:00 ~ 2026-04-17 10:00:00]",
            )

    def test_keyword_selection_can_sort_by_group_position(self):
        with TemporaryDirectory() as tmp:
            config_root = Path(tmp) / "config"
            _write_text(
                config_root / "custom" / "keyword" / "ordered.txt",
                """
                [WORD_GROUPS]
                [Later]
                Later

                [Earlier]
                Earlier
                """,
            )

            snapshot = HotlistSnapshot(
                mode="daily",
                generated_at="2026-04-17 11:00:00",
                items=[
                    HotlistItem(news_item_id="1", source_id="s1", source_name="Platform 1", title="Later item one", ranks=[5], current_rank=5),
                    HotlistItem(news_item_id="2", source_id="s1", source_name="Platform 1", title="Later item two", ranks=[6], current_rank=6),
                    HotlistItem(news_item_id="3", source_id="s1", source_name="Platform 1", title="Earlier item", ranks=[1], current_rank=1),
                ],
            )

            service = SelectionService(config_root=str(config_root), sort_by_position_first=True)
            result = service.run(snapshot, SelectionOptions(strategy="keyword", frequency_file="ordered.txt"))

            self.assertEqual([group.label for group in result.groups], ["Later", "Earlier"])
            self.assertEqual(result.total_selected, 3)

            view_model = build_render_view_model(
                LocalizedReport(
                    base_report=RenderableReport(
                        meta={"mode": "daily", "report_type": "每日报告"},
                        selection=result,
                        insight=InsightResult(),
                        display_regions=["hotlist"],
                    )
                ),
                display_mode="platform",
                rank_threshold=5,
            )
            self.assertEqual([group.label for group in view_model.hotlist_groups], ["Platform 1"])
            self.assertEqual(view_model.hotlist_groups[0].items[0].matched_keyword, "Earlier")

    def test_keyword_selection_result_feeds_native_render_section_model(self):
        with TemporaryDirectory() as tmp:
            config_root = Path(tmp) / "config"
            _write_text(
                config_root / "custom" / "keyword" / "render.txt",
                """
                [WORD_GROUPS]
                [AI]
                AI
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
                        first_time="09-00",
                        last_time="10-00",
                        count=3,
                        is_new=True,
                    ),
                ],
            )

            service = SelectionService(config_root=str(config_root))
            result = service.run(snapshot, SelectionOptions(strategy="keyword", frequency_file="render.txt"))
            localized = LocalizedReport(
                base_report=RenderableReport(
                    meta={
                        "mode": "current",
                        "report_type": "实时报告",
                    },
                    selection=result,
                    insight=InsightResult(),
                    display_regions=["hotlist"],
                )
            )
            view_model = build_render_view_model(localized, display_mode="keyword", rank_threshold=5)
            html = render_hotlist_stats_html(view_model.hotlist_groups, display_mode=view_model.display_mode)

            self.assertEqual(view_model.hotlist_groups[0].items[0].title, "AI launches new model")
            self.assertIn("Platform 1", html)
            self.assertIn("news-item new", html)
            self.assertIn("09:00~10:00", html)


if __name__ == "__main__":
    unittest.main()
