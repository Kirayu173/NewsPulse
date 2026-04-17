import unittest

from newspulse.context import AppContext
from newspulse.workflow import (
    HotlistItem,
    HotlistReportAssembler,
    HotlistSnapshot,
    InsightResult,
    InsightSection,
    SelectionGroup,
    SelectionResult,
    SourceFailure,
    StandaloneSection,
)


def _build_sample_stage_outputs():
    item = HotlistItem(
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
    extra = HotlistItem(
        news_item_id="2",
        source_id="producthunt",
        source_name="Product Hunt",
        title="Startup launches AI productivity app",
        current_rank=2,
        ranks=[2],
        first_time="2026-04-17 10:00:00",
        last_time="2026-04-17 10:00:00",
        count=1,
    )
    outsider = HotlistItem(
        news_item_id="3",
        source_id="hackernews",
        source_name="Hacker News",
        title="NBA finals schedule announced",
        current_rank=3,
        ranks=[3],
        first_time="2026-04-17 10:00:00",
        last_time="2026-04-17 10:00:00",
        count=1,
        is_new=True,
    )
    snapshot = HotlistSnapshot(
        mode="current",
        generated_at="2026-04-17 10:00:00",
        items=[item, extra, outsider],
        failed_sources=[SourceFailure(source_id="toutiao", source_name="今日头条", reason="timeout")],
        new_items=[item, outsider],
        standalone_sections=[
            StandaloneSection(key="producthunt", label="Product Hunt", items=[extra]),
        ],
        summary={"total_items": 3, "total_new_items": 2},
    )
    selection = SelectionResult(
        strategy="keyword",
        groups=[SelectionGroup(key="ai", label="AI", items=[item, extra], position=0)],
        selected_items=[item, extra],
        total_candidates=3,
        total_selected=2,
        diagnostics={"group_count": 1, "matched_candidates": 2},
    )
    insight = InsightResult(
        enabled=True,
        strategy="ai",
        sections=[InsightSection(key="core_trends", title="核心趋势", content="AI tools dominate the feed.")],
        raw_response='{"core_trends":"AI tools dominate the feed."}',
        diagnostics={"analyzed_items": 2, "section_count": 1},
    )
    return snapshot, selection, insight


class HotlistReportAssemblerTest(unittest.TestCase):
    def test_assembler_combines_native_stage_outputs_into_renderable_report(self):
        snapshot, selection, insight = _build_sample_stage_outputs()
        assembler = HotlistReportAssembler(
            display_regions=["hotlist", "new_items", "standalone", "ai_analysis", "hotlist"],
            timezone="Asia/Hong_Kong",
            display_mode="keyword",
        )

        report = assembler.assemble(snapshot, selection, insight)

        self.assertEqual(report.selection, selection)
        self.assertEqual(report.insight, insight)
        self.assertEqual(report.new_items, [snapshot.new_items[0]])
        self.assertEqual(report.selection.selected_new_items, [snapshot.new_items[0]])
        self.assertEqual(report.standalone_sections, snapshot.standalone_sections)
        self.assertEqual(report.display_regions, ["hotlist", "new_items", "standalone", "ai_analysis"])
        self.assertEqual(report.meta["mode"], "current")
        self.assertEqual(report.meta["report_type"], "实时报告")
        self.assertEqual(report.meta["timezone"], "Asia/Hong_Kong")
        self.assertEqual(report.meta["selection_strategy"], "keyword")
        self.assertEqual(report.meta["insight_strategy"], "ai")
        self.assertEqual(report.meta["total_items"], 3)
        self.assertEqual(report.meta["total_selected"], 2)
        self.assertEqual(report.meta["total_new_items"], 1)
        self.assertEqual(report.meta["total_failed_sources"], 1)
        self.assertEqual(report.meta["failed_sources"][0]["source_id"], "toutiao")
        self.assertEqual(report.meta["selection_diagnostics"]["group_count"], 1)
        self.assertEqual(report.meta["insight_diagnostics"]["section_count"], 1)


class AppContextRenderableReportTest(unittest.TestCase):
    def test_context_assemble_renderable_report_uses_project_defaults(self):
        snapshot, selection, insight = _build_sample_stage_outputs()
        ctx = AppContext(
            {
                "TIMEZONE": "Asia/Hong_Kong",
                "DISPLAY_MODE": "keyword",
                "DISPLAY": {
                    "REGION_ORDER": ["hotlist", "ai_analysis", "standalone"],
                },
            }
        )

        report = ctx.assemble_renderable_report(snapshot, selection, insight)

        self.assertEqual(report.display_regions, ["hotlist", "ai_analysis", "standalone"])
        self.assertEqual(report.meta["timezone"], "Asia/Hong_Kong")
        self.assertEqual(report.meta["display_mode"], "keyword")
        self.assertEqual(report.meta["report_type"], "实时报告")


if __name__ == "__main__":
    unittest.main()
