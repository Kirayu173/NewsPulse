import unittest

from newspulse.ai.client import AIClient


class AIClientTest(unittest.TestCase):
    def test_normalize_model_with_api_base_adds_openai_prefix(self):
        client = AIClient(
            {
                "MODEL": "glm-4.6v",
                "API_KEY": "test-key",
                "API_BASE": "https://open.bigmodel.cn/api/paas/v4/",
            }
        )

        self.assertEqual(client.model, "openai/glm-4.6v")


if __name__ == "__main__":
    unittest.main()
