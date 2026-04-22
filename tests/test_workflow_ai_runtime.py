import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from newspulse.workflow.shared.ai_runtime import (
    AIConfigError,
    AIInvocationError,
    AIRuntimeClient,
    AIRuntimeConfig,
    CachedAIRuntimeClient,
    AIResponseDecodeError,
    PromptTemplate,
    PromptTemplateNotFoundError,
    build_request_overrides,
    decode_json_response,
    load_prompt_template,
)


class AIRuntimePromptTest(unittest.TestCase):
    def test_load_prompt_template_splits_system_and_user_sections(self):
        with TemporaryDirectory() as tmp:
            config_root = Path(tmp)
            prompt_file = config_root / "ai" / "prompt.txt"
            prompt_file.parent.mkdir(parents=True, exist_ok=True)
            prompt_file.write_text(
                "[system]\nSystem prompt\n[user]\nUser prompt",
                encoding="utf-8",
            )

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
        prompt = PromptTemplate(
            path=Path("ai/prompt.txt"),
            system_prompt="system",
            user_prompt="user",
        )

        context = prompt.build_cache_context(operation="selection", prompt_name="classify")

        self.assertEqual(context["operation"], "selection")
        self.assertEqual(context["prompt_name"], "classify")
        self.assertEqual(context["prompt_path"], str(Path("ai/prompt.txt")))
        self.assertTrue(context["prompt_hash"])

    def test_load_prompt_template_raises_for_missing_required_file(self):
        with TemporaryDirectory() as tmp:
            config_root = Path(tmp)

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

    def test_runtime_client_builds_completion_request_and_normalizes_content(self):
        calls = []

        def fake_completion(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=[
                                {"text": "line one"},
                                {"text": "line two"},
                            ]
                        )
                    )
                ]
            )

        client = AIRuntimeClient(
            {
                "MODEL": "openai/test-model",
                "API_KEY": "test-key",
                "TEMPERATURE": 0.2,
                "MAX_TOKENS": 200,
                "TIMEOUT": 30,
                "NUM_RETRIES": 1,
            },
            completion_func=fake_completion,
        )

        result = client.chat([{"role": "user", "content": "hello"}])

        self.assertEqual(result, "line one\nline two")
        self.assertEqual(calls[0]["model"], "openai/test-model")
        self.assertEqual(calls[0]["temperature"], 0.2)
        self.assertEqual(calls[0]["max_tokens"], 200)

    def test_runtime_client_raises_typed_errors_for_config_and_invocation(self):
        client = AIRuntimeClient({"MODEL": "openai/test-model", "API_KEY": ""}, completion_func=lambda **_: None)
        with self.assertRaises(AIConfigError):
            client.chat([{"role": "user", "content": "hello"}])

        def raising_completion(**kwargs):
            raise RuntimeError("boom")

        client = AIRuntimeClient(
            {"MODEL": "openai/test-model", "API_KEY": "test-key"},
            completion_func=raising_completion,
        )
        with self.assertRaises(AIInvocationError):
            client.chat([{"role": "user", "content": "hello"}])

    def test_cached_runtime_client_reuses_identical_requests(self):
        calls = []

        def fake_completion(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=f"response-{len(calls)}"))]
            )

        client = CachedAIRuntimeClient(
            AIRuntimeClient(
                {"MODEL": "openai/test-model", "API_KEY": "test-key"},
                completion_func=fake_completion,
            ),
            ttl_seconds=600,
        )

        first = client.chat([{"role": "user", "content": "hello"}], temperature=0)
        second = client.chat([{"role": "user", "content": "hello"}], temperature=0)

        self.assertEqual(first, "response-1")
        self.assertEqual(second, "response-1")
        self.assertEqual(len(calls), 1)
        self.assertEqual(client.cache_stats()["hits"], 1)
        self.assertEqual(client.cache_stats()["misses"], 1)

    def test_cached_runtime_client_keeps_prompt_context_in_cache_key(self):
        calls = []

        def fake_completion(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=f"response-{len(calls)}"))]
            )

        client = CachedAIRuntimeClient(
            AIRuntimeClient(
                {"MODEL": "openai/test-model", "API_KEY": "test-key"},
                completion_func=fake_completion,
            ),
            ttl_seconds=600,
        )

        first = client.chat(
            [{"role": "user", "content": "hello"}],
            cache_context={"prompt_name": "item", "prompt_hash": "hash-a"},
        )
        second = client.chat(
            [{"role": "user", "content": "hello"}],
            cache_context={"prompt_name": "item", "prompt_hash": "hash-b"},
        )

        self.assertEqual(first, "response-1")
        self.assertEqual(second, "response-2")
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
