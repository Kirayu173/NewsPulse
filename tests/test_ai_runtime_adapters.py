import unittest
from types import SimpleNamespace

from newspulse.workflow.shared.ai_runtime.adapters.anthropic_chat import AnthropicChatAdapter
from newspulse.workflow.shared.ai_runtime.adapters.litellm_chat import LiteLLMChatAdapter
from newspulse.workflow.shared.ai_runtime.adapters.litellm_embedding import LiteLLMEmbeddingAdapter
from newspulse.workflow.shared.ai_runtime.adapters.openai_chat import OpenAIChatAdapter
from newspulse.workflow.shared.ai_runtime.adapters.openai_embedding import OpenAIEmbeddingAdapter
from newspulse.workflow.shared.ai_runtime.contracts import (
    ChatRequest,
    EmbeddingRequest,
    ResolvedChatRuntime,
    ResolvedEmbeddingRuntime,
)


class LiteLLMChatAdapterTest(unittest.TestCase):
    def test_chat_normalizes_litellm_content_blocks(self):
        calls = []

        def fake_completion(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content=[{"text": "line one"}, {"text": "line two"}]),
                        finish_reason="stop",
                    )
                ]
            )

        adapter = LiteLLMChatAdapter(completion_func=fake_completion)
        runtime = ResolvedChatRuntime(driver="litellm", model="deepseek/deepseek-chat", request_model="deepseek/deepseek-chat")
        request = ChatRequest(
            model="deepseek/deepseek-chat",
            messages=[{"role": "user", "content": "hello"}],
            max_tokens=256,
            api_key="test-key",
            fallbacks=("openai/gpt-4o-mini",),
        )

        response = adapter.chat(runtime, request)

        self.assertEqual(response.text, "line one\nline two")
        self.assertEqual(calls[0]["model"], "deepseek/deepseek-chat")
        self.assertEqual(calls[0]["fallbacks"], ["openai/gpt-4o-mini"])


class OpenAIAdapterTest(unittest.TestCase):
    def test_chat_uses_openai_sdk_client(self):
        calls = {}

        class FakeClient:
            def __init__(self, **kwargs):
                calls["init"] = kwargs
                self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

            def create(self, **kwargs):
                calls["chat"] = kwargs
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content="hello from openai"), finish_reason="stop")]
                )

        adapter = OpenAIChatAdapter(client_factory=FakeClient)
        runtime = ResolvedChatRuntime(
            driver="openai",
            model="openai/glm-4.6v",
            request_model="glm-4.6v",
            api_style="openai",
        )
        request = ChatRequest(
            model="glm-4.6v",
            messages=[{"role": "user", "content": "hello"}],
            api_key="test-key",
            api_base="https://provider.example/v1",
            temperature=0.3,
            max_tokens=128,
            timeout=45,
        )

        response = adapter.chat(runtime, request)

        self.assertEqual(response.text, "hello from openai")
        self.assertEqual(calls["init"]["base_url"], "https://provider.example/v1")
        self.assertEqual(calls["init"]["api_key"], "test-key")
        self.assertEqual(calls["chat"]["model"], "glm-4.6v")
        self.assertEqual(calls["chat"]["temperature"], 0.3)

    def test_embedding_uses_openai_sdk_client(self):
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
                    ]
                )

        adapter = OpenAIEmbeddingAdapter(client_factory=FakeClient)
        runtime = ResolvedEmbeddingRuntime(
            driver="openai",
            model="openai/text-embedding-3-small",
            request_model="text-embedding-3-small",
            api_style="openai",
            enabled=True,
        )
        request = EmbeddingRequest(
            model="text-embedding-3-small",
            inputs=["a", "b"],
            api_key="test-key",
            api_base="https://provider.example/v1",
            timeout=30,
        )

        response = adapter.embed(runtime, request)

        self.assertEqual(response.vectors, [[0.1, 0.2], [0.3, 0.4]])
        self.assertEqual(calls["init"]["base_url"], "https://provider.example/v1")
        self.assertEqual(calls["embed"]["model"], "text-embedding-3-small")


class AnthropicAdapterTest(unittest.TestCase):
    def test_chat_converts_messages_to_anthropic_format(self):
        calls = {}

        class FakeClient:
            def __init__(self, **kwargs):
                calls["init"] = kwargs
                self.messages = SimpleNamespace(create=self.create)

            def create(self, **kwargs):
                calls["chat"] = kwargs
                return SimpleNamespace(
                    content=[
                        SimpleNamespace(type="thinking", thinking="ignored"),
                        SimpleNamespace(type="text", text="hello"),
                        {"type": "text", "text": "world"},
                    ],
                    stop_reason="end_turn",
                )

        adapter = AnthropicChatAdapter(client_factory=FakeClient)
        runtime = ResolvedChatRuntime(
            driver="anthropic",
            model="anthropic/MiniMax-M2.7",
            request_model="MiniMax-M2.7",
            api_style="anthropic",
        )
        request = ChatRequest(
            model="MiniMax-M2.7",
            messages=[
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Hi"},
            ],
            api_key="test-key",
            api_base="https://api.minimaxi.com/anthropic",
            max_tokens=256,
        )

        response = adapter.chat(runtime, request)

        self.assertEqual(response.text, "hello\nworld")
        self.assertEqual(calls["init"]["base_url"], "https://api.minimaxi.com/anthropic")
        self.assertEqual(calls["chat"]["model"], "MiniMax-M2.7")
        self.assertEqual(calls["chat"]["system"], "You are helpful.")
        self.assertEqual(calls["chat"]["messages"][0]["content"], [{"type": "text", "text": "Hi"}])


class LiteLLMEmbeddingAdapterTest(unittest.TestCase):
    def test_embed_sorts_rows_by_index(self):
        def fake_embedding(**kwargs):
            return {
                "data": [
                    {"index": 1, "embedding": [0.3, 0.4]},
                    {"index": 0, "embedding": [0.1, 0.2]},
                ]
            }

        adapter = LiteLLMEmbeddingAdapter(embedding_func=fake_embedding)
        runtime = ResolvedEmbeddingRuntime(
            driver="litellm",
            model="openai/text-embedding-3-small",
            request_model="openai/text-embedding-3-small",
            enabled=True,
        )
        request = EmbeddingRequest(model="openai/text-embedding-3-small", inputs=["a", "b"])

        response = adapter.embed(runtime, request)

        self.assertEqual(response.vectors, [[0.1, 0.2], [0.3, 0.4]])


if __name__ == "__main__":
    unittest.main()
