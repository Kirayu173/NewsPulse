import unittest

import newspulse.notification as notification_pkg
from newspulse.context import AppContext
from newspulse.workflow import DeliveryPayload, DeliveryService, GenericWebhookDeliveryAdapter
from newspulse.workflow.shared.options import DeliveryOptions


class FakeSender:
    def __init__(self):
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(dict(kwargs))
        return True


class WorkflowDeliveryServiceTest(unittest.TestCase):
    def test_generic_webhook_adapter_sends_prepared_payloads_with_batch_headers(self):
        sender = FakeSender()
        adapter = GenericWebhookDeliveryAdapter(
            {
                "GENERIC_WEBHOOK_URL": "https://example.com/webhook",
                "GENERIC_WEBHOOK_TEMPLATE": "",
                "MESSAGE_BATCH_SIZE": 4000,
            },
            sender_func=sender,
        )
        payloads = [
            DeliveryPayload(channel="generic_webhook", title="Daily Report", content="Batch A"),
            DeliveryPayload(channel="generic_webhook", title="Daily Report", content="Batch B"),
        ]

        result = adapter.run(payloads)

        self.assertTrue(result.success)
        self.assertEqual(result.attempted_payloads, 2)
        self.assertEqual(result.delivered_payloads, 2)
        self.assertEqual(len(sender.calls), 2)
        self.assertTrue(sender.calls[0]["content"].startswith("**["))
        self.assertEqual(sender.calls[0]["title"], "Daily Report")

    def test_delivery_service_filters_channels_and_supports_dry_run(self):
        sender = FakeSender()
        service = DeliveryService(
            generic_webhook_adapter=GenericWebhookDeliveryAdapter(
                {
                    "GENERIC_WEBHOOK_URL": "https://example.com/webhook",
                    "MESSAGE_BATCH_SIZE": 4000,
                },
                sender_func=sender,
            )
        )
        payloads = [
            DeliveryPayload(channel="generic_webhook", title="Daily Report", content="Content A"),
            DeliveryPayload(channel="unknown", title="Daily Report", content="Content B"),
        ]

        result = service.run(
            payloads,
            DeliveryOptions(
                enabled=True,
                channels=["generic_webhook"],
                dry_run=True,
            ),
        )

        self.assertTrue(result.success)
        self.assertEqual(result.attempted_payloads, 1)
        self.assertEqual(result.delivered_payloads, 1)
        self.assertEqual(sender.calls, [])


class AppContextDeliveryStageTest(unittest.TestCase):
    def test_context_run_delivery_stage_uses_project_defaults(self):
        captured = {}

        class FakeDeliveryService:
            def run(self, payloads, options):
                captured["payloads"] = list(payloads)
                captured["options"] = options
                return {"ok": True}

        ctx = AppContext(
            {
                "ENABLE_NOTIFICATION": True,
                "GENERIC_WEBHOOK_URL": "https://example.com/webhook",
            }
        )
        payloads = [DeliveryPayload(channel="generic_webhook", title="Daily Report", content="Content A")]

        result = ctx.run_delivery_stage(payloads, dry_run=True, delivery_service=FakeDeliveryService())

        self.assertEqual(result, {"ok": True})
        self.assertEqual(len(captured["payloads"]), 1)
        self.assertTrue(captured["options"].enabled)
        self.assertEqual(captured["options"].channels, ["generic_webhook"])
        self.assertTrue(captured["options"].dry_run)


class NotificationCompatibilityCleanupTest(unittest.TestCase):
    def test_notification_package_no_longer_exports_legacy_dispatch_helpers(self):
        self.assertFalse(hasattr(notification_pkg, "NotificationDispatcher"))
        self.assertFalse(hasattr(notification_pkg, "send_to_generic_webhook"))


if __name__ == "__main__":
    unittest.main()
