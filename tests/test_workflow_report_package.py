import unittest

from newspulse.context import AppContext
from newspulse.workflow.report import ReportPackageAssembler
from newspulse.workflow.shared.contracts import (
    HotlistItem,
    HotlistSnapshot,
    InsightResult,
    ReportPackage,
    SelectionGroup,
    SelectionResult,
    SourceFailure,
)


def _build_stage_outputs(*, include_new_items: bool = True, include_failed_source: bool = False):
    selected_item = HotlistItem(
        news_item_id="item-1",
        source_id="hackernews",
        source_name="Hacker News",
        title="Agent runtime update",
        current_rank=1,
        ranks=[1, 2],
        first_time="2026-04-21 09:00:00",
        last_time="2026-04-21 10:00:00",
        count=2,
        is_new=include_new_items,
    )
    other_item = HotlistItem(
        news_item_id="item-2",
        source_id="producthunt",
        source_name="Product Hunt",
        title="Startup launch",
        current_rank=2,
        ranks=[2],
        first_time="2026-04-21 10:00:00",
        last_time="2026-04-21 10:00:00",
        count=1,
        is_new=include_new_items,
    )
    snapshot = HotlistSnapshot(
        mode="current",
        generated_at="2026-04-21 10:00:00",
        items=[selected_item, other_item],
        failed_sources=(
            [SourceFailure(source_id="weibo", source_name="Weibo", reason="timeout")]
            if include_failed_source
            else []
        ),
        new_items=[selected_item, other_item] if include_new_items else [],
        standalone_sections=[],
        summary={"total_items": 2},
    )
    selection = SelectionResult(
        strategy="keyword",
        groups=[SelectionGroup(key="ai", label="AI", items=[selected_item], position=0)],
        selected_items=[selected_item],
        selected_new_items=[other_item],
        total_candidates=2,
        total_selected=1,
        diagnostics={"group_count": 1},
    )
    insight = InsightResult(enabled=False, strategy="noop", diagnostics={"reason": "disabled"})
    return snapshot, selection, insight


class ReportPackageAssemblerTest(unittest.TestCase):
    def test_assembler_does_not_write_back_selected_new_items(self):
        snapshot, selection, insight = _build_stage_outputs(include_new_items=True)
        assembler = ReportPackageAssembler(timezone="Asia/Hong_Kong", display_mode="keyword")

        package = assembler.assemble(snapshot, selection, insight)

        self.assertIsInstance(package, ReportPackage)
        self.assertEqual(
            [item.news_item_id for item in selection.selected_new_items],
            ["item-2"],
        )
        self.assertEqual(
            [item.news_item_id for item in package.content.new_items],
            ["item-1"],
        )
        self.assertIsNot(package.content.hotlist_groups[0], selection.groups[0])
        self.assertEqual(package.integrity.errors, [])

    def test_assembler_builds_integrity_counters_and_skipped_regions(self):
        snapshot, selection, insight = _build_stage_outputs(
            include_new_items=False,
            include_failed_source=True,
        )
        assembler = ReportPackageAssembler(timezone="Asia/Hong_Kong", display_mode="platform")

        package = assembler.assemble(snapshot, selection, insight)

        self.assertTrue(package.integrity.valid)
        self.assertEqual(package.integrity.counters["snapshot_item_count"], 2)
        self.assertEqual(package.integrity.counters["selected_item_count"], 1)
        self.assertEqual(package.integrity.counters["hotlist_group_count"], 1)
        self.assertEqual(package.integrity.counters["new_item_count"], 0)
        self.assertEqual(package.integrity.counters["standalone_section_count"], 0)
        self.assertEqual(package.integrity.counters["insight_section_count"], 0)
        self.assertEqual(package.integrity.counters["failed_source_count"], 1)
        self.assertEqual(
            package.integrity.skipped_regions,
            ["new_items", "standalone"],
        )
        self.assertEqual(package.diagnostics["failed_sources"][0]["source_id"], "weibo")

    def test_assembler_backfills_canonical_snapshot_items_without_mutating_selection(self):
        snapshot_item = HotlistItem(
            news_item_id="item-1",
            source_id="hackernews",
            source_name="Hacker News",
            title="Agent runtime update",
            url="https://example.com/agent-runtime",
            mobile_url="https://m.example.com/agent-runtime",
            current_rank=1,
            ranks=[1, 2],
            first_time="2026-04-21 09:00:00",
            last_time="2026-04-21 10:00:00",
            count=2,
            metadata={"snapshot_tag": "canonical"},
        )
        snapshot = HotlistSnapshot(
            mode="current",
            generated_at="2026-04-21 10:00:00",
            items=[snapshot_item],
            new_items=[snapshot_item],
            summary={"total_items": 1},
        )
        skinny_selection_item = HotlistItem(
            news_item_id="item-1",
            source_id="hackernews",
            source_name="Hacker News",
            title="Agent runtime update",
            metadata={"selection_reason": "focus"},
        )
        missing_selection_item = HotlistItem(
            news_item_id="missing-item",
            source_id="producthunt",
            source_name="Product Hunt",
            title="Missing from snapshot",
        )
        selection = SelectionResult(
            strategy="ai",
            groups=[
                SelectionGroup(
                    key="focus",
                    label="Focus",
                    items=[skinny_selection_item],
                    position=0,
                )
            ],
            selected_items=[skinny_selection_item, missing_selection_item],
            total_candidates=2,
            total_selected=2,
        )
        insight = InsightResult(enabled=False, strategy="noop", diagnostics={"reason": "disabled"})
        assembler = ReportPackageAssembler(timezone="Asia/Hong_Kong", display_mode="keyword")

        package = assembler.assemble(snapshot, selection, insight)

        self.assertEqual(selection.selected_items[0].url, "")
        self.assertEqual(package.content.selected_items[0].url, "https://example.com/agent-runtime")
        self.assertEqual(
            package.content.hotlist_groups[0].items[0].mobile_url,
            "https://m.example.com/agent-runtime",
        )
        self.assertEqual(package.content.selected_items[0].metadata["snapshot_tag"], "canonical")
        self.assertEqual(package.content.selected_items[0].metadata["selection_reason"], "focus")
        self.assertEqual(package.integrity.counters["selected_item_count"], 1)
        self.assertTrue(any("missing-item" in error for error in package.integrity.errors))


class AppContextReportPackageTest(unittest.TestCase):
    def test_context_assembles_report_package_with_project_defaults(self):
        snapshot, selection, insight = _build_stage_outputs(include_new_items=True)
        ctx = AppContext(
            {
                "TIMEZONE": "Asia/Hong_Kong",
                "DISPLAY_MODE": "platform",
                "DISPLAY": {
                    "REGION_ORDER": ["hotlist", "insight", "new_items"],
                },
            }
        )

        assembler = ctx.create_report_assembler()
        package = ctx.assemble_report_package(snapshot, selection, insight)

        self.assertIsInstance(assembler, ReportPackageAssembler)
        self.assertEqual(package.meta.timezone, "Asia/Hong_Kong")
        self.assertEqual(package.meta.display_mode, "platform")
        self.assertEqual(package.meta.report_type, "实时报告")
        self.assertEqual(package.meta.selection_strategy, "keyword")


if __name__ == "__main__":
    unittest.main()
