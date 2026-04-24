import shutil
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from newspulse.workflow.selection.ai import build_embedding_runtime_config
from newspulse.workflow.shared.ai_runtime import (
    AIConfigError,
    AIInvocationError,
    AIResponseDecodeError,
    AIRuntimeClient,
    AIRuntimeConfig,
    CachedAIRuntimeClient,
    EmbeddingRuntimeClient,
    PromptTemplate,
    PromptTemplateNotFoundError,
    build_request_overrides,
    decode_json_response,
    load_prompt_template,
)

TEST_TMPDIR = Path(".tmp-test") / "workflow-ai-runtime"
TEST_TMPDIR.mkdir(parents=True, exist_ok=True)


@contextmanager
def workspace_tmpdir():
    path = TEST_TMPDIR / uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


class AIRuntimePromptTest(unittest.TestCase):
    def test_load_prompt_template_splits_system_and_user_sections(self):
        with workspace_tmpdir() as config_root:
            prompt_file = config_root / "ai" / "prompt.txt"
            prompt_file.parent.mkdir(parents=True, exist_ok=True)
            prompt_file.write_text("[system]\nSystem prompt\n[user]\nUser prompt", encoding="utf-8")

            prompt = load_prompt_template(
                "prompt.txt",
                config_root=config_root,
                config_subdir="ai",
                required=True,
            )

            self.assertEqual(prompt.system_prompt, "System prompt")
            self.assertEqual(prompt.user_prompt, "User prompt")
            self.assertEqual(
                prompt.build_messages(),
                [
                    {"role": "system", "content": "System prompt"},
                    {"role": "user", "content": "User prompt"},
                ],
            )

    def test_prompt_template_builds_cache_context(self):
        prompt = PromptTemplate(path=Path("ai/prompt.txt"), system_prompt="system", user_prompt="user")

        context = prompt.build_cache_context(operation="selection", prompt_name="classify")

        self.assertEqual(context["operation"], "selection")
        self.assertEqual(context["prompt_name"], "classify")
        self.assertEqual(context["prompt_path"], str(Path("ai/prompt.txt")))
        self.assertTrue(context["prompt_hash"])

    def test_load_prompt_template_raises_for_missing_required_file(self):
        with workspace_tmpdir() as config_root:

            with self.assertRaises(PromptTemplateNotFoundError) as ctx:
                load_prompt_template(
                    "missing.txt",
                    config_root=config_root,
                    config_subdir="ai",
                    required=True,
                )

            self.assertIn("missing.txt", str(ctx.exception))

    def test_build_request_overrides_merges_prompt_cache_scope(self):
        prompt = PromptTemplate(path=Path("prompt.txt"), user_prompt="hello")

        overrides = build_request_overrides(
            {
                "TIMEOUT": 45,
                "NUM_RETRIES": 3,
                "EXTRA_PARAMS": {"top_p": 0.9},
            },
            prompt_template=prompt,
            operation="insight",
            prompt_name="aggregate",
            overrides={"cache_context": {"attempt": 2}},
        )

        self.assertEqual(overrides["timeout"], 45)
        self.assertEqual(overrides["num_retries"], 3)
        self.assertEqual(overrides["top_p"], 0.9)
        self.assertEqual(overrides["cache_context"]["operation"], "insight")
        self.assertEqual(overrides["cache_context"]["prompt_name"], "aggregate")
        self.assertEqual(overrides["cache_context"]["attempt"], 2)


class AIRuntimeCodecTest(unittest.TestCase):
    def test_decode_json_response_repairs_fenced_json(self):
        response = """```json
        {"tags": [{"tag": "ai", "description": "AI",}],}
        ```"""

        parsed = decode_json_response(response)

        self.assertEqual(parsed["tags"][0]["tag"], "ai")

    def test_decode_json_response_raises_typed_error_for_invalid_payload(self):
        with self.assertRaises(AIResponseDecodeError):
            decode_json_response("not a json payload", repair=False)


class AIRuntimeClientTest(unittest.TestCase):
    def test_runtime_config_normalizes_plain_model_names_with_api_base(self):
        config = AIRuntimeConfig.from_mapping(
            {
                "MODEL": "glm-4.6v",
                "API_KEY": "test-key",
                "API_BASE": "https://open.bigmodel.cn/api/paas/v4/",
            }
        )

        self.assertEqual(config.model, "openai/glm-4.6v")

    def test_runtime_client_generates_text_and_preserves_result_metadata(self):
        calls = []

        class FakeClient:
            def __init__(self, **kwargs):
                calls.append({"init": kwargs})
                self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

            def create(self, **kwargs):
                calls.append({"chat": kwargs})
                return SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(content=[{"text": "line one"}, {"text": "line two"}]),
                            finish_reason="stop",
                        )
                    ],
                    usage=SimpleNamespace(prompt_tokens=3, completion_tokens=4, total_tokens=7),
                )

        with patch.dict("os.environ", {}, clear=True):
            client = AIRuntimeClient(
                {
                    "MODEL": "openai/test-model",
                    "API_KEY": "test-key",
                    "TEMPERATURE": 0.2,
                    "MAX_TOKENS": 200,
                    "TIMEOUT": 30,
                    "NUM_RETRIES": 1,
                },
                openai_client_factory=FakeClient,
            )

            result = client.generate_text([{"role": "user", "content": "hello"}])

        self.assertEqual(result.text, "line one\nline two")
        self.assertEqual(result.finish_reason, "stop")
        self.assertEqual(result.usage.total_tokens, 7)
        self.assertEqual(calls[1]["chat"]["model"], "test-model")
        self.assertEqual(calls[1]["chat"]["temperature"], 0.2)
        self.assertEqual(calls[1]["chat"]["max_tokens"], 200)

    def test_runtime_client_generates_json(self):
        class FakeClient:
            def __init__(self, **kwargs):
                self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

            def create(self, **kwargs):
                return SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(content='{"status": "ok", "count": 2}'),
                            finish_reason="stop",
                        )
                    ],
                    usage=None,
                )

        client = AIRuntimeClient(
            {"MODEL": "openai/test-model", "API_KEY": "test-key"},
            openai_client_factory=FakeClient,
        )
        result = client.generate_json([{"role": "user", "content": "hello"}])

        self.assertEqual(result.json_payload, {"status": "ok", "count": 2})

    def test_runtime_client_raises_typed_errors_for_config_and_invocation(self):
        with patch.dict("os.environ", {}, clear=True):
            client = AIRuntimeClient({"MODEL": "openai/test-model", "API_KEY": ""})
            with self.assertRaises(AIConfigError):
                client.generate_text([{"role": "user", "content": "hello"}])

            class RaisingClient:
                def __init__(self, **kwargs):
                    self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

                def create(self, **kwargs):
                    raise RuntimeError("boom")

            client = AIRuntimeClient(
                {"MODEL": "openai/test-model", "API_KEY": "test-key"},
                openai_client_factory=RaisingClient,
            )
            with self.assertRaises(AIInvocationError):
                client.generate_text([{"role": "user", "content": "hello"}])

    def test_runtime_client_rejects_invalid_anthropic_temperature(self):
        client = AIRuntimeClient(
            {
                "MODEL": "MiniMax-M2.7",
                "API_KEY": "test-key",
                "API_BASE": "https://api.minimaxi.com/anthropic",
                "TEMPERATURE": 0,
            }
        )

        with self.assertRaises(AIConfigError):
            client.generate_text([{"role": "user", "content": "hello"}])

    def test_runtime_client_rejects_invalid_minimax_openai_temperature(self):
        client = AIRuntimeClient(
            {
                "MODEL": "MiniMax-M2.7",
                "API_KEY": "test-key",
                "API_BASE": "https://api.minimaxi.com/v1",
                "PROVIDER_FAMILY": "openai",
                "TEMPERATURE": 0,
            }
        )

        with self.assertRaises(AIConfigError):
            client.generate_text([{"role": "user", "content": "hello"}])

    def test_runtime_client_routes_anthropic_style_base_to_anthropic_sdk(self):
        calls = {}

        class FakeClient:
            def __init__(self, **kwargs):
                calls["init"] = kwargs
                self.messages = SimpleNamespace(create=self.create)

            def create(self, **kwargs):
                calls["chat"] = kwargs
                return SimpleNamespace(
                    content=[SimpleNamespace(type="text", text="anthropic-response")],
                    stop_reason="end_turn",
                    usage=None,
                )

        client = AIRuntimeClient(
            {
                "MODEL": "MiniMax-M2.7",
                "API_KEY": "test-key",
                "API_BASE": "https://api.minimaxi.com/anthropic",
            },
            anthropic_client_factory=FakeClient,
        )

        result = client.generate_text([{"role": "user", "content": "hello"}])

        self.assertEqual(result.text, "anthropic-response")
        self.assertEqual(client.resolve_runtime().provider_family, "anthropic")
        self.assertEqual(calls["chat"]["model"], "MiniMax-M2.7")
        self.assertEqual(calls["init"]["base_url"], "https://api.minimaxi.com/anthropic")

    def test_runtime_client_accepts_openai_native_sdk_env_vars(self):
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
                            message=SimpleNamespace(content="openai-response"),
                            finish_reason="stop",
                        )
                    ],
                    usage=None,
                )

        with patch.dict(
            "os.environ",
            {
                "OPENAI_API_KEY": "sdk-openai-key",
                "OPENAI_BASE_URL": "https://provider.example/v1",
            },
            clear=True,
        ):
            client = AIRuntimeClient(
                {
                    "MODEL": "glm-4.6v",
                    "PROVIDER_FAMILY": "openai",
                },
                openai_client_factory=FakeClient,
            )

            result = client.generate_text([{"role": "user", "content": "hello"}])
            runtime = client.resolve_runtime()

        self.assertEqual(result.text, "openai-response")
        self.assertEqual(runtime.provider_family, "openai")
        self.assertEqual(runtime.api_base, "https://provider.example/v1")
        self.assertEqual(calls["init"]["api_key"], "sdk-openai-key")
        self.assertEqual(calls["init"]["base_url"], "https://provider.example/v1")
        self.assertEqual(calls["chat"]["model"], "glm-4.6v")

    def test_runtime_client_accepts_anthropic_native_sdk_env_vars(self):
        calls = {}

        class FakeClient:
            def __init__(self, **kwargs):
                calls["init"] = kwargs
                self.messages = SimpleNamespace(create=self.create)

            def create(self, **kwargs):
                calls["chat"] = kwargs
                return SimpleNamespace(
                    content=[SimpleNamespace(type="text", text="anthropic-response")],
                    stop_reason="end_turn",
                    usage=None,
                )

        with patch.dict(
            "os.environ",
            {
                "ANTHROPIC_API_KEY": "sdk-anthropic-key",
                "ANTHROPIC_BASE_URL": "https://api.minimaxi.com/anthropic",
            },
            clear=True,
        ):
            client = AIRuntimeClient(
                {
                    "MODEL": "MiniMax-M2.7",
                },
                anthropic_client_factory=FakeClient,
            )

            result = client.generate_text([{"role": "user", "content": "hello"}])
            runtime = client.resolve_runtime()

        self.assertEqual(result.text, "anthropic-response")
        self.assertEqual(runtime.provider_family, "anthropic")
        self.assertEqual(runtime.api_base, "https://api.minimaxi.com/anthropic")
        self.assertEqual(calls["init"]["api_key"], "sdk-anthropic-key")
        self.assertEqual(calls["init"]["base_url"], "https://api.minimaxi.com/anthropic")
        self.assertEqual(calls["chat"]["model"], "MiniMax-M2.7")

    def test_cached_runtime_client_reuses_identical_requests(self):
        class FakeClient:
            counter = 0

            def __init__(self, **kwargs):
                self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

            def create(self, **kwargs):
                FakeClient.counter += 1
                return SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(content=f"response-{FakeClient.counter}"),
                            finish_reason="stop",
                        )
                    ],
                    usage=None,
                )

        with patch.dict("os.environ", {}, clear=True):
            client = CachedAIRuntimeClient(
                AIRuntimeClient(
                    {"MODEL": "openai/test-model", "API_KEY": "test-key"},
                    openai_client_factory=FakeClient,
                ),
                ttl_seconds=600,
            )

            first = client.generate_text([{"role": "user", "content": "hello"}], temperature=0)
            second = client.generate_text([{"role": "user", "content": "hello"}], temperature=0)

        self.assertEqual(first.text, "response-1")
        self.assertEqual(second.text, "response-1")
        self.assertEqual(client.cache_stats()["hits"], 1)
        self.assertEqual(client.cache_stats()["misses"], 1)

    def test_cached_runtime_client_keeps_prompt_context_in_cache_key(self):
        class FakeClient:
            counter = 0

            def __init__(self, **kwargs):
                self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

            def create(self, **kwargs):
                FakeClient.counter += 1
                return SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(content=f"response-{FakeClient.counter}"),
                            finish_reason="stop",
                        )
                    ],
                    usage=None,
                )

        with patch.dict("os.environ", {}, clear=True):
            client = CachedAIRuntimeClient(
                AIRuntimeClient(
                    {"MODEL": "openai/test-model", "API_KEY": "test-key"},
                    openai_client_factory=FakeClient,
                ),
                ttl_seconds=600,
            )

            first = client.generate_text(
                [{"role": "user", "content": "hello"}],
                cache_context={"prompt_name": "item", "prompt_hash": "hash-a"},
            )
            second = client.generate_text(
                [{"role": "user", "content": "hello"}],
                cache_context={"prompt_name": "item", "prompt_hash": "hash-b"},
            )

        self.assertEqual(first.text, "response-1")
        self.assertEqual(second.text, "response-2")


class EmbeddingRuntimeClientTest(unittest.TestCase):
    def test_embedding_runtime_config_prefers_embedding_specific_env_fields(self):
        with patch.dict(
            "os.environ",
            {
                "AI_EMBEDDING_MODEL": "text-embedding-3-small",
                "AI_EMBEDDING_API_KEY": "embedding-key",
                "AI_EMBEDDING_BASE_URL": "https://provider.example/v1",
                "AI_EMBEDDING_PROVIDER_FAMILY": "openai",
            },
            clear=True,
        ):
            config = build_embedding_runtime_config(
                {
                    "MODEL": "openai/chat-model",
                    "API_KEY": "chat-key",
                    "API_BASE": "https://chat.example/v1",
                    "PROVIDER_FAMILY": "openai",
                }
            )

        self.assertEqual(config["MODEL"], "openai/text-embedding-3-small")
        self.assertEqual(config["API_KEY"], "embedding-key")
        self.assertEqual(config["API_BASE"], "https://provider.example/v1")
        self.assertEqual(config["PROVIDER_FAMILY"], "openai")

    def test_embedding_runtime_client_is_disabled_without_model(self):
        client = EmbeddingRuntimeClient({})

        self.assertFalse(client.is_enabled())


if __name__ == "__main__":
    unittest.main()
