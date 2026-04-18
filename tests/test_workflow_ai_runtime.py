import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from newspulse.workflow.shared.ai_runtime import (
    AIConfigError,
    AIInvocationError,
    AIRuntimeClient,
    AIRuntimeConfig,
    AIResponseDecodeError,
    PromptTemplateNotFoundError,
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


if __name__ == "__main__":
    unittest.main()
