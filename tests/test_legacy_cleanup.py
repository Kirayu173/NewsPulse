import importlib
import unittest

import newspulse.notification as notification_pkg
import newspulse.storage as storage_pkg
import newspulse.workflow as workflow_pkg
import newspulse.workflow.insight as insight_pkg
import newspulse.workflow.selection as selection_pkg


class LegacyCleanupTest(unittest.TestCase):
    def test_report_package_has_been_removed_after_render_consolidation(self):
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("newspulse.report")
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("newspulse.pipeline")

    def test_storage_package_no_longer_exports_sqlite_mixin_shim(self):
        self.assertFalse(hasattr(storage_pkg, "SQLiteStorageMixin"))

    def test_notification_package_keeps_only_batch_and_sender_exports(self):
        self.assertTrue(hasattr(notification_pkg, "send_prepared_generic_webhook"))
        self.assertTrue(hasattr(notification_pkg, "add_batch_headers"))
        self.assertFalse(hasattr(notification_pkg, "send_to_generic_webhook"))
        self.assertFalse(hasattr(notification_pkg, "NotificationDispatcher"))
        self.assertFalse(hasattr(notification_pkg, "split_content_into_batches"))
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("newspulse.notification.splitter")

    def test_workflow_render_package_no_longer_exports_render_legacy_adapter(self):
        self.assertFalse(hasattr(workflow_pkg, "LegacyRenderContext"))
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("newspulse.workflow.render.legacy")

    def test_workflow_packages_no_longer_export_legacy_or_localization_adapters(self):
        self.assertFalse(hasattr(insight_pkg, "to_ai_analysis_result"))
        self.assertFalse(hasattr(selection_pkg, "selection_result_to_legacy_stats"))
        self.assertFalse(hasattr(insight_pkg, "AIInsightStrategy"))
        self.assertFalse(hasattr(insight_pkg, "NoopInsightStrategy"))
        self.assertFalse(hasattr(selection_pkg, "AISelectionStrategy"))
        self.assertFalse(hasattr(selection_pkg, "KeywordSelectionStrategy"))
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("newspulse.workflow.localization")
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("newspulse.workflow.insight.legacy")
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("newspulse.workflow.selection.legacy")

    def test_render_defaults_no_longer_use_ai_analysis_region_name(self):
        from newspulse.context import AppContext
        from newspulse.workflow.shared.options import RenderOptions

        self.assertEqual(RenderOptions().display_regions, ["hotlist", "new_items", "standalone", "insight"])
        self.assertEqual(AppContext({}).region_order, ["hotlist", "new_items", "standalone", "insight"])

    def test_core_package_no_longer_exports_workflow_domain_helpers(self):
        import newspulse.core as core_pkg

        self.assertFalse(hasattr(core_pkg, "calculate_news_weight"))
        self.assertFalse(hasattr(core_pkg, "count_word_frequency"))
        self.assertFalse(hasattr(core_pkg, "format_time_display"))
        self.assertFalse(hasattr(core_pkg, "load_frequency_words"))
        self.assertFalse(hasattr(core_pkg, "matches_word_groups"))
        self.assertFalse(hasattr(core_pkg, "read_all_today_titles"))
        self.assertFalse(hasattr(core_pkg, "detect_latest_new_titles"))
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("newspulse.core.analyzer")
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("newspulse.core.frequency")
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("newspulse.core.data")

    def test_ai_package_no_longer_exports_legacy_translation_stack(self):
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("newspulse.ai")
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
