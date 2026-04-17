import unittest

from newspulse.context import AppContext
from newspulse.notification.dispatcher import NotificationDispatcher
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
            DeliveryPayload(channel="generic_webhook", title="实时报告", content="第一批内容"),
            DeliveryPayload(channel="generic_webhook", title="实时报告", content="第二批内容"),
        ]

        result = adapter.run(payloads)

        self.assertTrue(result.success)
        self.assertEqual(result.attempted_payloads, 2)
        self.assertEqual(result.delivered_payloads, 2)
        self.assertEqual(len(sender.calls), 2)
        self.assertTrue(sender.calls[0]["content"].startswith("**["))
        self.assertEqual(sender.calls[0]["title"], "实时报告")

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
            DeliveryPayload(channel="generic_webhook", title="实时报告", content="内容A"),
            DeliveryPayload(channel="unknown", title="实时报告", content="内容B"),
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
        payloads = [DeliveryPayload(channel="generic_webhook", title="实时报告", content="内容A")]

        result = ctx.run_delivery_stage(payloads, dry_run=True, delivery_service=FakeDeliveryService())

        self.assertEqual(result, {"ok": True})
        self.assertEqual(len(captured["payloads"]), 1)
        self.assertTrue(captured["options"].enabled)
        self.assertEqual(captured["options"].channels, ["generic_webhook"])
        self.assertTrue(captured["options"].dry_run)


class NotificationDispatcherPreparedPayloadTest(unittest.TestCase):
    def test_dispatch_payloads_routes_prepared_generic_webhook_payloads(self):
        sender = FakeSender()
        dispatcher = NotificationDispatcher(
            config={
                "GENERIC_WEBHOOK_URL": "https://example.com/webhook",
                "MESSAGE_BATCH_SIZE": 4000,
            },
            generic_webhook_sender=sender,
        )
        payloads = [
            DeliveryPayload(channel="generic_webhook", title="实时报告", content="内容A"),
            DeliveryPayload(channel="generic_webhook", title="实时报告", content="内容B"),
        ]

        results = dispatcher.dispatch_payloads(payloads)

        self.assertEqual(results, {"generic_webhook": True})
        self.assertEqual(len(sender.calls), 2)

    def test_dispatcher_no_longer_exposes_legacy_dispatch_all_wrapper(self):
        self.assertFalse(hasattr(NotificationDispatcher, "dispatch_all"))


if __name__ == "__main__":
    unittest.main()
