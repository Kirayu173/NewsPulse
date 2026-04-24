import os
import unittest
from pathlib import Path

from newspulse.workflow.shared.ai_runtime import AIRuntimeClient, EmbeddingRuntimeClient


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class LiveAIRuntimeCompatibilityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        project_root = Path(__file__).resolve().parents[1]
        _load_dotenv(project_root / ".env")
        if os.environ.get("NEWSPULSE_RUN_LIVE_AI_TESTS") != "1":
            raise unittest.SkipTest("live AI tests disabled")

        api_key = os.environ.get("AI_API_KEY") or os.environ.get("API_KEY") or ""
        model = os.environ.get("AI_MODEL") or os.environ.get("MODEL") or ""
        if not api_key or not model:
            raise unittest.SkipTest("live AI credentials are incomplete")

        cls.openai_client = AIRuntimeClient(
            {
                "MODEL": model,
                "API_KEY": api_key,
                "API_BASE": "https://api.minimaxi.com/v1",
                "PROVIDER_FAMILY": "openai",
                "TEMPERATURE": 1.0,
                "MAX_TOKENS": 512,
                "TIMEOUT": 120,
            }
        )
        cls.anthropic_client = AIRuntimeClient(
            {
                "MODEL": model,
                "API_KEY": api_key,
                "API_BASE": "https://api.minimaxi.com/anthropic",
                "PROVIDER_FAMILY": "anthropic",
                "TEMPERATURE": 1.0,
                "MAX_TOKENS": 512,
                "TIMEOUT": 120,
            }
        )

    def test_openai_runtime_preserves_json_usage_finish_reason_and_reasoning(self):
        result = self.openai_client.generate_json(
            [
                {"role": "system", "content": "Return valid JSON only."},
                {"role": "user", "content": 'Return {"provider":"minimax","sum":12} where sum is 5+7.'},
            ],
            extra_body={"reasoning_split": True},
        )

        reasoning_details = getattr(result.provider_response.choices[0].message, "reasoning_details", None) or []
        self.assertEqual(result.provider_family, "openai")
        self.assertEqual(result.finish_reason, "stop")
        self.assertEqual(result.json_payload, {"provider": "minimax", "sum": 12})
        self.assertIsNotNone(result.usage)
        self.assertIsNotNone(result.provider_response)
        self.assertEqual(len(result.thinking_blocks), len(reasoning_details))

    def test_openai_runtime_supports_tool_continuity(self):
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get weather of a location.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {"type": "string", "description": "City and country"},
                        },
                        "required": ["location"],
                    },
                },
            }
        ]
        first = self.openai_client.generate_native(
            [
                {"role": "system", "content": "Use tools when required."},
                {"role": "user", "content": "What is the weather in Shanghai today? Use the get_weather tool first."},
            ],
            tools=tools,
            tool_choice="auto",
            extra_body={"reasoning_split": True},
        )

        self.assertEqual(first.finish_reason, "tool_calls")
        self.assertGreaterEqual(len(first.tool_calls), 1)
        self.assertIsNotNone(first.continuation_payload)

        second = self.openai_client.generate_text(
            [
                {"role": "system", "content": "Use tools when required."},
                {"role": "user", "content": "What is the weather in Shanghai today? Use the get_weather tool first."},
                first.continuation_payload,
                {
                    "role": "tool",
                    "tool_call_id": first.tool_calls[0]["id"],
                    "content": "27 degrees C and sunny",
                },
            ],
            tools=tools,
            tool_choice="auto",
            extra_body={"reasoning_split": True},
        )

        self.assertEqual(second.finish_reason, "stop")
        self.assertTrue(second.text.strip())
        self.assertIn("27", second.text)

    def test_anthropic_runtime_preserves_json_usage_finish_reason_and_blocks(self):
        result = self.anthropic_client.generate_json(
            [
                {"role": "system", "content": "Return valid JSON only."},
                {
                    "role": "user",
                    "content": [{"type": "text", "text": 'Return {"provider":"minimax","product":42} where product is 6*7.'}],
                },
            ],
            thinking={"type": "enabled", "budget_tokens": 256},
        )

        provider_block_types = [getattr(block, "type", "") for block in getattr(result.provider_response, "content", []) or []]
        self.assertEqual(result.provider_family, "anthropic")
        self.assertEqual(result.finish_reason, "end_turn")
        self.assertEqual(result.json_payload, {"provider": "minimax", "product": 42})
        self.assertIsNotNone(result.usage)
        self.assertIsNotNone(result.provider_response)
        self.assertEqual([block.type for block in result.blocks], provider_block_types)

    def test_anthropic_runtime_supports_tool_continuity(self):
        tools = [
            {
                "name": "get_weather",
                "description": "Get weather of a location.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "City and country"},
                    },
                    "required": ["location"],
                },
            }
        ]
        first = self.anthropic_client.generate_native(
            [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "You must call the get_weather tool exactly once before answering. What is the weather in Shanghai today?",
                        }
                    ],
                },
            ],
            tools=tools,
            tool_choice={"type": "auto"},
            thinking={"type": "enabled", "budget_tokens": 128},
            temperature=0.2,
            max_tokens=1024,
        )

        self.assertGreaterEqual(len(first.tool_calls), 1)
        self.assertIsNotNone(first.continuation_payload)
        self.assertTrue(any(block["type"] == "tool_use" for block in first.continuation_payload["content"]))

        second = self.anthropic_client.generate_text(
            [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "You must call the get_weather tool exactly once before answering. What is the weather in Shanghai today?",
                        }
                    ],
                },
                first.continuation_payload,
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": first.tool_calls[0]["id"],
                            "content": "27 degrees C and sunny",
                        }
                    ],
                },
            ],
            tools=tools,
            tool_choice={"type": "auto"},
            thinking={"type": "enabled", "budget_tokens": 128},
            temperature=0.2,
            max_tokens=1024,
        )

        self.assertEqual(second.finish_reason, "end_turn")
        self.assertTrue(second.text.strip())
        self.assertIn("27", second.text)

    def test_embedding_runtime_runs_if_embedding_model_is_configured(self):
        embedding_model = os.environ.get("AI_EMBEDDING_MODEL") or os.environ.get("EMB_MODEL") or ""
        if not embedding_model:
            self.skipTest("live embedding model is not configured")

        client = EmbeddingRuntimeClient(
            {
                "MODEL": embedding_model,
                "API_KEY": os.environ.get("AI_EMBEDDING_API_KEY") or os.environ.get("AI_API_KEY") or os.environ.get("API_KEY") or "",
                "API_BASE": os.environ.get("AI_EMBEDDING_BASE_URL") or os.environ.get("AI_EMBEDDING_API_BASE") or "https://api.minimaxi.com/v1",
                "PROVIDER_FAMILY": "openai",
                "TIMEOUT": 120,
            }
        )

        result = client.generate_embeddings(["provider native runtime", "anthropic tool continuity"])

        self.assertEqual(len(result.vectors), 2)
        self.assertTrue(all(vector for vector in result.vectors))
        self.assertIsNotNone(result.provider_response)


if __name__ == "__main__":
    unittest.main()
