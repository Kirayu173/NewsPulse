import unittest

from newspulse.workflow.shared.ai_runtime.client import AIRuntimeConfig


class AIClientTest(unittest.TestCase):
    def test_normalize_model_with_api_base_adds_openai_prefix(self):
        config = AIRuntimeConfig.from_mapping(
            {
                "MODEL": "glm-4.6v",
                "API_KEY": "test-key",
                "API_BASE": "https://open.bigmodel.cn/api/paas/v4/",
            }
        )

        self.assertEqual(config.model, "openai/glm-4.6v")


if __name__ == "__main__":
    unittest.main()
