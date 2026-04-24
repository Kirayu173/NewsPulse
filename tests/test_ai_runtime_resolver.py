import unittest

from newspulse.workflow.shared.ai_runtime.resolver import (
    detect_api_style,
    resolve_chat_runtime,
    resolve_embedding_runtime,
)


class AIRuntimeResolverTest(unittest.TestCase):
    def test_detect_api_style_recognizes_anthropic_endpoints(self):
        self.assertEqual(detect_api_style("https://api.minimaxi.com/anthropic"), "anthropic")
        self.assertEqual(detect_api_style("https://example.com/v1"), "openai")

    def test_resolve_chat_runtime_routes_plain_model_to_anthropic_sdk(self):
        runtime = resolve_chat_runtime(
            {
                "MODEL": "MiniMax-M2.7",
                "API_KEY": "test-key",
                "API_BASE": "https://api.minimaxi.com/anthropic",
            }
        )

        self.assertEqual(runtime["provider_family"], "anthropic")
        self.assertEqual(runtime["model"], "anthropic/MiniMax-M2.7")
        self.assertEqual(runtime["request_model"], "MiniMax-M2.7")
        self.assertEqual(runtime["api_style"], "anthropic")

    def test_resolve_chat_runtime_routes_plain_model_to_openai_sdk(self):
        runtime = resolve_chat_runtime(
            {
                "MODEL": "glm-4.6v",
                "API_KEY": "test-key",
                "API_BASE": "https://open.bigmodel.cn/api/paas/v4/",
            }
        )

        self.assertEqual(runtime["provider_family"], "openai")
        self.assertEqual(runtime["model"], "openai/glm-4.6v")
        self.assertEqual(runtime["request_model"], "glm-4.6v")
        self.assertEqual(runtime["api_style"], "openai")

    def test_resolve_chat_runtime_preserves_vendor_prefixed_openai_models(self):
        runtime = resolve_chat_runtime({"MODEL": "deepseek/deepseek-chat", "API_KEY": "test-key"})

        self.assertEqual(runtime["provider_family"], "openai")
        self.assertEqual(runtime["model"], "deepseek/deepseek-chat")
        self.assertEqual(runtime["request_model"], "deepseek/deepseek-chat")

    def test_resolve_embedding_runtime_routes_plain_model_to_openai_sdk(self):
        runtime = resolve_embedding_runtime(
            {
                "MODEL": "text-embedding-3-small",
                "API_KEY": "test-key",
                "API_BASE": "https://api.openai.com/v1",
            }
        )

        self.assertEqual(runtime["provider_family"], "openai")
        self.assertEqual(runtime["model"], "openai/text-embedding-3-small")
        self.assertEqual(runtime["request_model"], "text-embedding-3-small")
        self.assertTrue(runtime["enabled"])

    def test_resolve_embedding_runtime_is_disabled_without_model(self):
        runtime = resolve_embedding_runtime({"API_KEY": "test-key"})

        self.assertEqual(runtime["provider_family"], "openai")
        self.assertEqual(runtime["model"], "")
        self.assertEqual(runtime["request_model"], "")
        self.assertFalse(runtime["enabled"])


if __name__ == "__main__":
    unittest.main()
