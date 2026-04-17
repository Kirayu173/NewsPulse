import unittest

from newspulse.workflow import (
    WORKFLOW_STAGE_NAMES,
    DeliveryOptions,
    DeliveryPayload,
    DeliveryStage,
    HotlistItem,
    HotlistSnapshot,
    InsightOptions,
    InsightResult,
    InsightSection,
    InsightStage,
    LocalizationOptions,
    LocalizationScope,
    LocalizationStage,
    LocalizedReport,
    RenderOptions,
    RenderStage,
    RenderableReport,
    ReportAssembler,
    SelectionGroup,
    SelectionOptions,
    SelectionResult,
    SelectionStage,
    SnapshotBuilder,
    SnapshotOptions,
    SourceFailure,
    StandaloneSection,
    WorkflowOptions,
)


class WorkflowContractsTest(unittest.TestCase):
    def test_workflow_package_exports_stage_names_and_default_options(self):
        options = WorkflowOptions()

        self.assertEqual(
            WORKFLOW_STAGE_NAMES,
            ("snapshot", "selection", "insight", "localization", "render", "delivery"),
        )
        self.assertEqual(options.snapshot.mode, "current")
        self.assertEqual(options.selection.strategy, "keyword")
        self.assertEqual(options.selection.ai.interests_file, "ai_interests.txt")
        self.assertEqual(options.insight.strategy, "noop")
        self.assertFalse(options.localization.enabled)
        self.assertEqual(options.localization.language, "Chinese")
        self.assertEqual(
            options.render.display_regions,
            ["hotlist", "new_items", "standalone", "ai_analysis"],
        )
        self.assertTrue(options.delivery.enabled)

    def test_shared_contracts_form_a_single_native_workflow_payload_chain(self):
        item = HotlistItem(
            news_item_id="weibo:1:hello-world",
            source_id="weibo",
            source_name="微博",
            title="Hello World",
            url="https://example.com/item",
            current_rank=1,
            ranks=[1, 2, 3],
            first_time="2026-04-16 09:00:00",
            last_time="2026-04-16 10:00:00",
            count=3,
            is_new=True,
        )
        snapshot = HotlistSnapshot(
            mode="current",
            generated_at="2026-04-16 10:00:00",
            items=[item],
            failed_sources=[SourceFailure(source_id="toutiao", reason="timeout")],
            new_items=[item],
            standalone_sections=[StandaloneSection(key="tech", label="科技", items=[item])],
            summary={"total_items": 1},
        )
        selection = SelectionResult(
            strategy="keyword",
            groups=[SelectionGroup(key="ai", label="AI", items=[item], position=1)],
            selected_items=[item],
            selected_new_items=[item],
            total_candidates=1,
            total_selected=1,
        )
        insight = InsightResult(
            enabled=True,
            strategy="ai",
            sections=[InsightSection(key="trend", title="趋势", content="测试洞察")],
            raw_response="{\"trend\": \"测试洞察\"}",
        )
        report = RenderableReport(
            meta={"mode": snapshot.mode},
            selection=selection,
            insight=insight,
            new_items=selection.selected_new_items,
            standalone_sections=snapshot.standalone_sections,
            display_regions=["hotlist", "ai_analysis"],
        )
        localized = LocalizedReport(
            base_report=report,
            localized_titles={item.news_item_id: "你好，世界"},
            localized_sections={"trend": "Localized trend"},
            language="English",
        )
        payload = DeliveryPayload(
            channel="generic_webhook",
            title="NewsPulse report",
            content="content",
            metadata={"language": localized.language},
        )

        self.assertEqual(snapshot.item_count, 1)
        self.assertEqual(selection.selected_items[0].news_item_id, item.news_item_id)
        self.assertEqual(selection.selected_new_items[0].news_item_id, item.news_item_id)
        self.assertEqual(insight.sections[0].key, "trend")
        self.assertEqual(localized.base_report.selection.total_selected, 1)
        self.assertEqual(payload.metadata["language"], "English")

    def test_runtime_protocols_accept_stage_like_services(self):
        class FakeSnapshotBuilder:
            def build(self, options: SnapshotOptions) -> HotlistSnapshot:
                return HotlistSnapshot(mode=options.mode, generated_at="2026-04-16 10:00:00")

        class FakeSelectionStage:
            def run(self, snapshot: HotlistSnapshot, options: SelectionOptions) -> SelectionResult:
                return SelectionResult(strategy=options.strategy, total_candidates=snapshot.item_count)

        class FakeInsightStage:
            def run(
                self,
                snapshot: HotlistSnapshot,
                selection: SelectionResult,
                options: InsightOptions,
            ) -> InsightResult:
                return InsightResult(enabled=options.enabled, strategy=selection.strategy)

        class FakeReportAssembler:
            def assemble(
                self,
                snapshot: HotlistSnapshot,
                selection: SelectionResult,
                insight: InsightResult,
            ) -> RenderableReport:
                return RenderableReport(
                    meta={"mode": snapshot.mode},
                    selection=selection,
                    insight=insight,
                )

        class FakeLocalizationStage:
            def run(self, report: RenderableReport, options: LocalizationOptions) -> LocalizedReport:
                return LocalizedReport(base_report=report, language=options.language)

        class FakeRenderStage:
            def run(self, report: LocalizedReport, options: RenderOptions) -> dict:
                return {"report": report, "regions": options.display_regions}

        class FakeDeliveryStage:
            def run(self, payloads, options: DeliveryOptions) -> dict:
                return {"sent": options.enabled, "count": len(list(payloads))}

        self.assertIsInstance(FakeSnapshotBuilder(), SnapshotBuilder)
        self.assertIsInstance(FakeSelectionStage(), SelectionStage)
        self.assertIsInstance(FakeInsightStage(), InsightStage)
        self.assertIsInstance(FakeReportAssembler(), ReportAssembler)
        self.assertIsInstance(FakeLocalizationStage(), LocalizationStage)
        self.assertIsInstance(FakeRenderStage(), RenderStage)
        self.assertIsInstance(FakeDeliveryStage(), DeliveryStage)

    def test_localization_scope_defaults_follow_native_design(self):
        scope = LocalizationScope()

        self.assertTrue(scope.selection_titles)
        self.assertTrue(scope.new_items)
        self.assertTrue(scope.standalone)
        self.assertFalse(scope.insight_sections)


if __name__ == "__main__":
    unittest.main()
