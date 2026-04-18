import importlib
import unittest

import newspulse.notification as notification_pkg
import newspulse.report as report_pkg
import newspulse.storage as storage_pkg
import newspulse.ai as ai_pkg
import newspulse.workflow as workflow_pkg
import newspulse.workflow.insight as insight_pkg
import newspulse.workflow.localization as localization_pkg
import newspulse.workflow.selection as selection_pkg


class LegacyCleanupTest(unittest.TestCase):
    def test_report_package_no_longer_exports_generator_helpers(self):
        self.assertFalse(hasattr(report_pkg, "prepare_report_data"))
        self.assertFalse(hasattr(report_pkg, "generate_html_report"))

    def test_storage_package_no_longer_exports_sqlite_mixin_shim(self):
        self.assertFalse(hasattr(storage_pkg, "SQLiteStorageMixin"))

    def test_notification_package_keeps_only_prepared_sender_exports(self):
        self.assertTrue(hasattr(notification_pkg, "send_prepared_generic_webhook"))
        self.assertFalse(hasattr(notification_pkg, "send_to_generic_webhook"))
        self.assertFalse(hasattr(notification_pkg, "NotificationDispatcher"))

    def test_workflow_render_package_no_longer_exports_render_legacy_adapter(self):
        self.assertFalse(hasattr(workflow_pkg, "LegacyRenderContext"))
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("newspulse.workflow.render.legacy")

    def test_workflow_packages_no_longer_export_insight_or_selection_legacy_adapters(self):
        self.assertFalse(hasattr(insight_pkg, "to_ai_analysis_result"))
        self.assertFalse(hasattr(selection_pkg, "selection_result_to_legacy_stats"))
        self.assertFalse(hasattr(insight_pkg, "AIInsightStrategy"))
        self.assertFalse(hasattr(insight_pkg, "NoopInsightStrategy"))
        self.assertFalse(hasattr(selection_pkg, "AISelectionStrategy"))
        self.assertFalse(hasattr(selection_pkg, "KeywordSelectionStrategy"))
        self.assertFalse(hasattr(localization_pkg, "AILocalizationStrategy"))
        self.assertFalse(hasattr(localization_pkg, "NoopLocalizationStrategy"))
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("newspulse.workflow.insight.legacy")
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("newspulse.workflow.selection.legacy")

    def test_render_defaults_no_longer_use_ai_analysis_region_name(self):
        from newspulse.context import AppContext
        from newspulse.workflow.shared.options import RenderOptions

        self.assertEqual(RenderOptions().display_regions, ["hotlist", "new_items", "standalone", "insight"])
        self.assertEqual(AppContext({}).region_order, ["hotlist", "new_items", "standalone", "insight"])

    def test_ai_package_no_longer_exports_legacy_translation_stack(self):
        self.assertFalse(hasattr(ai_pkg, "AITranslator"))
        self.assertFalse(hasattr(ai_pkg, "TranslationResult"))
        self.assertFalse(hasattr(ai_pkg, "BatchTranslationResult"))
        self.assertFalse(hasattr(ai_pkg, "AIAnalyzer"))
        self.assertFalse(hasattr(ai_pkg, "AIAnalysisResult"))
        self.assertFalse(hasattr(ai_pkg, "AIFilter"))
        self.assertFalse(hasattr(ai_pkg, "AIFilterResult"))
        self.assertFalse(hasattr(ai_pkg, "get_ai_analysis_renderer"))
        self.assertFalse(hasattr(ai_pkg, "render_ai_analysis_markdown"))
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("newspulse.ai.translator")
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("newspulse.ai.client")
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("newspulse.ai.prompt_loader")
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("newspulse.ai.analyzer")
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("newspulse.ai.filter")
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("newspulse.ai.formatter")


if __name__ == "__main__":
    unittest.main()
