import importlib
import unittest

import newspulse.notification as notification_pkg
import newspulse.report as report_pkg
import newspulse.storage as storage_pkg
import newspulse.workflow as workflow_pkg


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


if __name__ == "__main__":
    unittest.main()
