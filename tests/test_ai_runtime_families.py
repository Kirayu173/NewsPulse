import unittest
from types import SimpleNamespace

from newspulse.workflow.shared.ai_runtime.contracts import (
    ChatRequest,
    EmbeddingRequest,
    ResolvedChatRuntime,
    ResolvedEmbeddingRuntime,
)
from newspulse.workflow.shared.ai_runtime.families import AnthropicFamilyRuntime, OpenAIFamilyRuntime


class OpenAIFamilyRuntimeTest(unittest.TestCase):
    def test_generate_uses_openai_sdk_client(self):
        calls = {}

        class FakeClient:
            def __init__(self, **kwargs):
                calls["init"] = kwargs
                self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

            def create(self, **kwargs):
                calls["chat"] = kwargs
                return SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(content="hello from openai"),
                            finish_reason="stop",
                        )
                    ],
                    usage=SimpleNamespace(prompt_tokens=12, completion_tokens=7, total_tokens=19),
                )

        runtime = OpenAIFamilyRuntime(client_factory=FakeClient)
        response = runtime.generate(
            ResolvedChatRuntime(
                provider_family="openai",
                model="openai/gpt-4o-mini",
                request_model="gpt-4o-mini",
                api_style="openai",
            ),
            ChatRequest(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "hello"}],
                api_key="test-key",
                api_base="https://provider.example/v1",
                temperature=0.3,
                max_tokens=128,
                timeout=45,
                num_retries=1,
            ),
        )

        self.assertEqual(response.text, "hello from openai")
        self.assertEqual(response.finish_reason, "stop")
        self.assertEqual(response.usage.total_tokens, 19)
        self.assertEqual(calls["init"]["base_url"], "https://provider.example/v1")
        self.assertEqual(calls["chat"]["model"], "gpt-4o-mini")
        self.assertEqual(calls["chat"]["temperature"], 0.3)

    def test_generate_preserves_reasoning_details_and_continuation_payload(self):
        class FakeToolCall:
            def __init__(self):
                self.id = "call-1"
                self.type = "function"
                self.function = SimpleNamespace(name="get_weather", arguments='{"location":"Shanghai"}')

            def model_dump(self):
                return {
                    "id": self.id,
                    "type": self.type,
                    "function": {
                        "name": self.function.name,
                        "arguments": self.function.arguments,
                    },
                }

        class FakeMessage:
            role = "assistant"
            content = ""
            reasoning_details = [{"type": "reasoning", "text": "Need to call the weather tool."}]
            tool_calls = [FakeToolCall()]

            def model_dump(self):
                return {
                    "role": self.role,
                    "content": self.content,
                    "reasoning_details": list(self.reasoning_details),
                    "tool_calls": [tool_call.model_dump() for tool_call in self.tool_calls],
                }

        class FakeClient:
            def __init__(self, **kwargs):
                self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

            def create(self, **kwargs):
                return SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=FakeMessage(),
                            finish_reason="tool_calls",
                        )
                    ],
                    usage=None,
                )

        runtime = OpenAIFamilyRuntime(client_factory=FakeClient)
        response = runtime.generate(
            ResolvedChatRuntime(
                provider_family="openai",
                model="openai/gpt-4o-mini",
                request_model="gpt-4o-mini",
                api_style="openai",
            ),
            ChatRequest(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "hello"}],
                api_key="test-key",
            ),
        )

        self.assertEqual(response.finish_reason, "tool_calls")
        self.assertEqual(len(response.thinking_blocks), 1)
        self.assertEqual(response.thinking_blocks[0].payload["text"], "Need to call the weather tool.")
        self.assertEqual(response.tool_calls[0]["function"]["name"], "get_weather")
        self.assertEqual(response.continuation_payload["role"], "assistant")
        self.assertEqual(response.continuation_payload["tool_calls"][0]["id"], "call-1")
        self.assertEqual(response.continuation_payload["reasoning_details"][0]["type"], "reasoning")
        self.assertEqual(response.diagnostics["reasoning_detail_count"], 1)

    def test_generate_json_decodes_payload(self):
        class FakeClient:
            def __init__(self, **kwargs):
                self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

            def create(self, **kwargs):
                return SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(content='{"ok": true, "count": 2}'),
                            finish_reason="stop",
                        )
                    ],
                    usage=None,
                )

        runtime = OpenAIFamilyRuntime(client_factory=FakeClient)
        response = runtime.generate(
            ResolvedChatRuntime(
                provider_family="openai",
                model="openai/gpt-4o-mini",
                request_model="gpt-4o-mini",
            ),
            ChatRequest(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "hello"}],
                response_mode="json",
                api_key="test-key",
            ),
        )

        self.assertEqual(response.json_payload, {"ok": True, "count": 2})

    def test_embed_uses_openai_sdk_client(self):
        calls = {}

        class FakeClient:
            def __init__(self, **kwargs):
                calls["init"] = kwargs
                self.embeddings = SimpleNamespace(create=self.create)

            def create(self, **kwargs):
                calls["embed"] = kwargs
                return SimpleNamespace(
                    data=[
                        SimpleNamespace(embedding=[0.1, 0.2]),
                        SimpleNamespace(embedding=[0.3, 0.4]),
                    ],
                    usage=SimpleNamespace(prompt_tokens=5, total_tokens=5),
                )

        runtime = OpenAIFamilyRuntime(client_factory=FakeClient)
        response = runtime.embed(
            ResolvedEmbeddingRuntime(
                provider_family="openai",
                model="openai/text-embedding-3-small",
                request_model="text-embedding-3-small",
                api_style="openai",
                enabled=True,
            ),
            EmbeddingRequest(
                model="text-embedding-3-small",
                inputs=["a", "b"],
                api_key="test-key",
                api_base="https://provider.example/v1",
                timeout=30,
            ),
        )

        self.assertEqual(response.vectors, ((0.1, 0.2), (0.3, 0.4)))
        self.assertEqual(calls["init"]["base_url"], "https://provider.example/v1")
        self.assertEqual(calls["embed"]["model"], "text-embedding-3-small")


class AnthropicFamilyRuntimeTest(unittest.TestCase):
    def test_generate_preserves_blocks_thinking_and_tool_calls(self):
        calls = {}

        class FakeClient:
            def __init__(self, **kwargs):
                calls["init"] = kwargs
                self.messages = SimpleNamespace(create=self.create)

            def create(self, **kwargs):
                calls["chat"] = kwargs
                return SimpleNamespace(
                    content=[
                        SimpleNamespace(type="thinking", thinking="intermediate reasoning"),
                        SimpleNamespace(type="tool_use", id="tool-1", name="lookup", input={"query": "x"}),
                        SimpleNamespace(type="text", text='{"answer": "done"}'),
                    ],
                    stop_reason="end_turn",
                    usage=SimpleNamespace(input_tokens=8, output_tokens=4, total_tokens=12),
                )

        runtime = AnthropicFamilyRuntime(client_factory=FakeClient)
        response = runtime.generate(
            ResolvedChatRuntime(
                provider_family="anthropic",
                model="anthropic/claude-sonnet-4-5",
                request_model="claude-sonnet-4-5",
                api_style="anthropic",
            ),
            ChatRequest(
                model="claude-sonnet-4-5",
                messages=[
                    {"role": "system", "content": "You are helpful."},
                    {"role": "user", "content": "Hi"},
                ],
                response_mode="json",
                api_key="test-key",
                api_base="https://provider.example/anthropic",
                max_tokens=256,
            ),
        )

        self.assertEqual(response.json_payload, {"answer": "done"})
        self.assertEqual(response.finish_reason, "end_turn")
        self.assertEqual(len(response.blocks), 3)
        self.assertEqual(len(response.thinking_blocks), 1)
        self.assertEqual(response.tool_calls[0]["name"], "lookup")
        self.assertEqual(response.continuation_payload["role"], "assistant")
        self.assertEqual(calls["chat"]["system"], "You are helpful.")
        self.assertEqual(calls["chat"]["messages"][0]["content"], [{"type": "text", "text": "Hi"}])


if __name__ == "__main__":
    unittest.main()
