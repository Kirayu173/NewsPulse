import os
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from newspulse.core.frequency import load_frequency_words
from newspulse.core.loader import load_config


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip(), encoding="utf-8")


class LoaderConfigRootTest(unittest.TestCase):
    def test_load_config_uses_project_config_root_and_ignores_parent_env(self):
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            project = workspace / "project"
            config_dir = project / "config"
            config_dir.mkdir(parents=True)

            (workspace / ".env").write_text(
                "API_KEY=parent-key\nBASE_URL=https://parent.example/v1\nMODEL=openai/parent-model\n",
                encoding="utf-8",
            )
            _write_text(
                config_dir / "config.yaml",
                """
                app:
                  timezone: Asia/Shanghai
                schedule:
                  enabled: false
                  preset: always_on
                ai:
                  model: openai/yaml-model
                  api_key: ""
                  api_base: ""
                """,
            )

            with patch("newspulse.core.config_paths.get_project_root", return_value=project):
                with patch.dict(os.environ, {}, clear=True):
                    config = load_config()

            self.assertEqual(config["AI"]["MODEL"], "openai/yaml-model")
            self.assertEqual(config["AI"]["API_KEY"], "")
            self.assertEqual(config["AI"]["API_BASE"], "")
            self.assertEqual(config["_PATHS"]["PROJECT_ROOT"], str(project))
            self.assertEqual(config["_PATHS"]["CONFIG_ROOT"], str(config_dir))
            self.assertEqual(config["_PATHS"]["CONFIG_PATH"], str(config_dir / "config.yaml"))

    def test_load_config_resolves_relative_config_path_from_project_root(self):
        with TemporaryDirectory() as tmp:
            project = Path(tmp)
            config_dir = project / "configs" / "dev"
            _write_text(
                config_dir / "config.yaml",
                """
                app:
                  timezone: Asia/Shanghai
                schedule:
                  enabled: true
                  preset: all_day
                ai:
                  model: should-not-win
                  api_key: ""
                  api_base: ""
                """,
            )
            _write_text(config_dir / "ai_analysis_prompt.txt", "[user]\nhello")
            _write_text(config_dir / "ai_translation_prompt.txt", "[user]\ntranslate")
            _write_text(config_dir / "ai_filter" / "prompt.txt", "[user]\nclassify")
            _write_text(config_dir / "ai_filter" / "extract_prompt.txt", "[user]\nextract")
            _write_text(config_dir / "ai_filter" / "update_tags_prompt.txt", "[user]\nupdate")

            env = {
                "CONFIG_PATH": "configs/dev/config.yaml",
                "AI_API_KEY": "env-key",
                "AI_API_BASE": "https://example.com/v1",
                "AI_MODEL": "openai/env-model",
            }
            with patch("newspulse.core.config_paths.get_project_root", return_value=project):
                with patch.dict(os.environ, env, clear=True):
                    config = load_config()

            self.assertEqual(config["AI"]["API_KEY"], "env-key")
            self.assertEqual(config["AI"]["API_BASE"], "https://example.com/v1")
            self.assertEqual(config["AI"]["MODEL"], "openai/env-model")
            self.assertEqual(config["_PATHS"]["CONFIG_ROOT"], str(config_dir))
            self.assertEqual(config["_PATHS"]["CONFIG_PATH"], str(config_dir / "config.yaml"))
            self.assertEqual(
                config["AI_ANALYSIS"]["PROMPT_FILE"],
                str(config_dir / "ai_analysis_prompt.txt"),
            )
            self.assertEqual(
                config["AI_TRANSLATION"]["PROMPT_FILE"],
                str(config_dir / "ai_translation_prompt.txt"),
            )
            self.assertEqual(
                config["AI_FILTER"]["PROMPT_FILE"],
                str(config_dir / "ai_filter" / "prompt.txt"),
            )

    def test_load_config_builds_independent_ai_runtime_configs(self):
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            config_dir = workspace / "config"
            config_file = config_dir / "config.yaml"
            _write_text(
                config_file,
                """
                app:
                  timezone: Asia/Shanghai
                schedule:
                  enabled: false
                  preset: always_on
                ai:
                  model: openai/base-model
                  api_key: base-key
                  timeout: 120
                  temperature: 0.5
                  max_tokens: 5000
                  num_retries: 1
                ai_analysis:
                  model: openai/analysis-model
                  timeout: 240
                ai_translation:
                  api_key: translation-key
                  temperature: 0.2
                ai_filter:
                  timeout: 480
                  num_retries: 0
                  max_tokens: 2000
                """,
            )

            with patch.dict(os.environ, {}, clear=True):
                config = load_config(str(config_file))

            self.assertEqual(config["AI"]["MODEL"], "openai/base-model")
            self.assertEqual(config["AI_ANALYSIS_MODEL"]["MODEL"], "openai/analysis-model")
            self.assertEqual(config["AI_ANALYSIS_MODEL"]["TIMEOUT"], 240)
            self.assertEqual(config["AI_TRANSLATION_MODEL"]["API_KEY"], "translation-key")
            self.assertEqual(config["AI_TRANSLATION_MODEL"]["TEMPERATURE"], 0.2)
            self.assertEqual(config["AI_FILTER_MODEL"]["TIMEOUT"], 480)
            self.assertEqual(config["AI_FILTER_MODEL"]["NUM_RETRIES"], 0)
            self.assertEqual(config["AI_FILTER_MODEL"]["MAX_TOKENS"], 2000)
            self.assertEqual(config["AI"]["TIMEOUT"], 120)
            self.assertEqual(config["AI"]["NUM_RETRIES"], 1)


class FrequencyWordsPathTest(unittest.TestCase):
    def test_load_frequency_words_resolves_custom_short_name_from_config_root(self):
        with TemporaryDirectory() as tmp:
            project = Path(tmp)
            config_dir = project / "config"
            _write_text(
                config_dir / "custom" / "keyword" / "weekly.txt",
                """
                [WORD_GROUPS]
                AI
                """,
            )

            word_groups, filter_words, global_filters = load_frequency_words(
                "weekly.txt",
                config_root=config_dir,
            )

            self.assertEqual(len(word_groups), 1)
            self.assertEqual(word_groups[0]["group_key"], "AI")
            self.assertEqual(filter_words, [])
            self.assertEqual(global_filters, [])


if __name__ == "__main__":
    unittest.main()
