import os
import shutil
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from newspulse.core.config_paths import resolve_ai_interests_path
from newspulse.core.loader import load_config
from newspulse.workflow.selection.frequency import load_keyword_rule_set
from tests.helpers.io import write_text

TEST_TMPDIR = Path(".tmp-test") / "loader"
TEST_TMPDIR.mkdir(parents=True, exist_ok=True)


@contextmanager
def workspace_tmpdir():
    path = TEST_TMPDIR / uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


class LoaderConfigRootTest(unittest.TestCase):
    def test_load_config_reads_unified_ai_env_from_project_root(self):
        with workspace_tmpdir() as project:
            config_dir = project / "config"
            config_dir.mkdir(parents=True)
            (project / ".env").write_text(
                "AI_API_KEY=dotenv-key\n"
                "AI_BASE_URL=https://dotenv.example/v1\n"
                "AI_MODEL=glm-4.6v\n",
                encoding="utf-8",
            )
            write_text(
                config_dir / "config.yaml",
                """
                app:
                  timezone: Asia/Shanghai
                schedule:
                  enabled: false
                  preset: always_on
                workflow:
                  selection:
                    strategy: ai
                    semantic:
                      enabled: true
                ai:
                  runtime:
                    model: deepseek/deepseek-chat
                    api_key: ""
                    api_base: ""
                """,
            )

            with patch("newspulse.core.config_paths.get_project_root", return_value=project):
                with patch.dict(os.environ, {}, clear=True):
                    config = load_config()

            self.assertEqual(config["AI"]["API_KEY"], "dotenv-key")
            self.assertEqual(config["AI"]["API_BASE"], "https://dotenv.example/v1")
            self.assertEqual(config["AI"]["MODEL"], "glm-4.6v")

    def test_load_config_reads_unified_ai_env_settings(self):
        with workspace_tmpdir() as project:
            config_dir = project / "config"
            config_dir.mkdir(parents=True)
            (project / ".env").write_text(
                "AI_API_KEY=dotenv-key\n"
                "AI_BASE_URL=https://dotenv.example/v1\n"
                "AI_MODEL=glm-4.6v\n"
                "AI_PROVIDER_FAMILY=openai\n",
                encoding="utf-8",
            )
            write_text(
                config_dir / "config.yaml",
                """
                app:
                  timezone: Asia/Shanghai
                schedule:
                  enabled: false
                  preset: always_on
                ai:
                  runtime:
                    model: deepseek/deepseek-chat
                    api_key: ""
                    api_base: ""
                    provider_family: auto
                """,
            )

            with patch("newspulse.core.config_paths.get_project_root", return_value=project):
                with patch.dict(os.environ, {}, clear=True):
                    config = load_config()

            self.assertEqual(config["AI"]["API_KEY"], "dotenv-key")
            self.assertEqual(config["AI"]["API_BASE"], "https://dotenv.example/v1")
            self.assertEqual(config["AI"]["MODEL"], "glm-4.6v")
            self.assertEqual(config["AI"]["PROVIDER_FAMILY"], "openai")

    def test_load_config_reads_provider_native_sdk_env_settings(self):
        with workspace_tmpdir() as project:
            config_dir = project / "config"
            config_dir.mkdir(parents=True)
            (project / ".env").write_text(
                "AI_MODEL=MiniMax-M2.7\n"
                "ANTHROPIC_API_KEY=dotenv-key\n"
                "ANTHROPIC_BASE_URL=https://api.minimaxi.com/anthropic\n",
                encoding="utf-8",
            )
            write_text(
                config_dir / "config.yaml",
                """
                app:
                  timezone: Asia/Shanghai
                schedule:
                  enabled: false
                  preset: always_on
                ai:
                  runtime:
                    model: ''
                    api_key: ''
                    api_base: ''
                    provider_family: auto
                """,
            )

            with patch("newspulse.core.config_paths.get_project_root", return_value=project):
                with patch.dict(os.environ, {}, clear=True):
                    config = load_config()

            self.assertEqual(config["AI"]["MODEL"], "MiniMax-M2.7")
            self.assertEqual(config["AI"]["API_KEY"], "dotenv-key")
            self.assertEqual(config["AI"]["API_BASE"], "https://api.minimaxi.com/anthropic")
            self.assertEqual(config["AI"]["PROVIDER_FAMILY"], "auto")

    def test_load_config_uses_project_config_root_and_ignores_parent_env(self):
        with workspace_tmpdir() as workspace:
            project = workspace / "project"
            config_dir = project / "config"
            config_dir.mkdir(parents=True)

            (workspace / ".env").write_text(
                "AI_API_KEY=parent-key\n"
                "AI_BASE_URL=https://parent.example/v1\n"
                "AI_MODEL=openai/parent-model\n",
                encoding="utf-8",
            )
            write_text(
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
        with workspace_tmpdir() as project:
            config_dir = project / "configs" / "dev"
            write_text(
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
            write_text(config_dir / "global_insight_prompt.txt", "[user]\nhello")
            write_text(config_dir / "ai_filter" / "prompt.txt", "[user]\nclassify")
            write_text(config_dir / "ai_filter" / "extract_prompt.txt", "[user]\nextract")
            write_text(config_dir / "ai_filter" / "update_tags_prompt.txt", "[user]\nupdate")

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
                str(config_dir / "global_insight_prompt.txt"),
            )
            self.assertEqual(
                config["AI_FILTER"]["PROMPT_FILE"],
                str(config_dir / "ai_filter" / "prompt.txt"),
            )

    def test_load_config_builds_independent_ai_runtime_configs(self):
        with workspace_tmpdir() as workspace:
            config_dir = workspace / "config"
            config_file = config_dir / "config.yaml"
            write_text(
                config_file,
                """
                app:
                  timezone: Asia/Shanghai
                schedule:
                  enabled: false
                  preset: always_on
                ai:
                  runtime:
                    model: openai/base-model
                    api_key: base-key
                    timeout: 120
                    temperature: 0.5
                    max_tokens: 5000
                    num_retries: 1
                  operations:
                    insight:
                      model: openai/analysis-model
                      timeout: 240
                    selection:
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
            self.assertEqual(config["AI_FILTER_MODEL"]["TIMEOUT"], 480)
            self.assertEqual(config["AI_FILTER_MODEL"]["NUM_RETRIES"], 0)
            self.assertEqual(config["AI_FILTER_MODEL"]["MAX_TOKENS"], 2000)
            self.assertEqual(config["AI"]["TIMEOUT"], 120)
            self.assertEqual(config["AI"]["NUM_RETRIES"], 1)

    def test_load_config_reads_logging_settings_from_advanced_section(self):
        with workspace_tmpdir() as workspace:
            config_dir = workspace / "config"
            config_file = config_dir / "config.yaml"
            write_text(
                config_file,
                """
                app:
                  timezone: Asia/Shanghai
                schedule:
                  enabled: false
                  preset: always_on
                advanced:
                  log_level: DEBUG
                  log_file: logs/newspulse.log
                  log_json: true
                """,
            )

            with patch.dict(os.environ, {}, clear=True):
                config = load_config(str(config_file))

            self.assertEqual(config["LOG_LEVEL"], "DEBUG")
            self.assertEqual(config["LOG_FILE"], "logs/newspulse.log")
            self.assertTrue(config["LOG_JSON"])

    def test_load_config_accepts_storage_retention_days_env_alias(self):
        with workspace_tmpdir() as workspace:
            config_dir = workspace / "config"
            config_file = config_dir / "config.yaml"
            write_text(
                config_file,
                """
                app:
                  timezone: Asia/Shanghai
                schedule:
                  enabled: false
                  preset: always_on
                storage:
                  local:
                    retention_days: 3
                """,
            )

            with patch.dict(os.environ, {"STORAGE_RETENTION_DAYS": "14"}, clear=True):
                config = load_config(str(config_file))

            self.assertEqual(config["STORAGE"]["LOCAL"]["RETENTION_DAYS"], 14)

    def test_load_config_supports_workflow_stage_sections_and_ai_operations(self):
        with workspace_tmpdir() as workspace:
            config_dir = workspace / "config"
            config_file = config_dir / "config.yaml"
            write_text(config_dir / "global_insight_prompt.txt", "[user]\nanalysis")
            write_text(config_dir / "ai_filter" / "prompt.txt", "[user]\nfilter")
            write_text(config_dir / "ai_filter" / "extract_prompt.txt", "[user]\nextract")
            write_text(config_dir / "ai_filter" / "update_tags_prompt.txt", "[user]\nupdate")
            write_text(
                config_file,
                """
                app:
                  timezone: Asia/Shanghai
                schedule:
                  enabled: false
                  preset: always_on
                workflow:
                  selection:
                    strategy: ai
                    frequency_file: topics.txt
                    priority_sort_enabled: true
                    ai:
                      interests_file: founders.txt
                      batch_size: 25
                      batch_interval: 1.5
                      min_score: 0.65
                      reclassify_threshold: 0.55
                      fallback_to_keyword: false
                    semantic:
                      enabled: true
                      top_k: 4
                      min_score: 0.61
                      direct_threshold: 0.83
                  insight:
                    enabled: true
                    strategy: ai
                    mode: daily
                    max_items: 9
                    language: Japanese
                ai:
                  runtime:
                    model: openai/base-model
                    api_key: base-key
                    api_base: https://base.example/v1
                    timeout: 111
                    temperature: 0.3
                    max_tokens: 4000
                    num_retries: 2
                  operations:
                    selection:
                      prompt_file: ai_filter/prompt.txt
                      extract_prompt_file: ai_filter/extract_prompt.txt
                      update_tags_prompt_file: ai_filter/update_tags_prompt.txt
                      model: openai/selection-model
                      timeout: 222
                      runtime_cache:
                        enabled: true
                        ttl_seconds: 900
                        max_entries: 128
                      extra_params:
                        top_p: 0.9
                    insight:
                      prompt_file: global_insight_prompt.txt
                      api_key: insight-key
                      temperature: 0.8
                      runtime_cache:
                        enabled: false
                        ttl_seconds: 60
                        max_entries: 16
                """,
            )

            with patch.dict(os.environ, {}, clear=True):
                config = load_config(str(config_file))

            self.assertEqual(config["WORKFLOW"]["SELECTION"]["STRATEGY"], "ai")
            self.assertEqual(config["WORKFLOW"]["SELECTION"]["FREQUENCY_FILE"], "topics.txt")
            self.assertTrue(config["WORKFLOW"]["SELECTION"]["PRIORITY_SORT_ENABLED"])
            self.assertEqual(config["WORKFLOW"]["SELECTION"]["AI"]["INTERESTS_FILE"], "founders.txt")
            self.assertEqual(config["WORKFLOW"]["SELECTION"]["AI"]["BATCH_SIZE"], 25)
            self.assertAlmostEqual(config["WORKFLOW"]["SELECTION"]["AI"]["BATCH_INTERVAL"], 1.5)
            self.assertAlmostEqual(config["WORKFLOW"]["SELECTION"]["AI"]["MIN_SCORE"], 0.65)
            self.assertAlmostEqual(config["WORKFLOW"]["SELECTION"]["AI"]["RECLASSIFY_THRESHOLD"], 0.55)
            self.assertFalse(config["WORKFLOW"]["SELECTION"]["AI"]["FALLBACK_TO_KEYWORD"])
            self.assertTrue(config["WORKFLOW"]["SELECTION"]["SEMANTIC"]["ENABLED"])
            self.assertEqual(config["WORKFLOW"]["SELECTION"]["SEMANTIC"]["TOP_K"], 4)
            self.assertAlmostEqual(config["WORKFLOW"]["SELECTION"]["SEMANTIC"]["MIN_SCORE"], 0.61)
            self.assertAlmostEqual(config["WORKFLOW"]["SELECTION"]["SEMANTIC"]["DIRECT_THRESHOLD"], 0.83)

            self.assertTrue(config["WORKFLOW"]["INSIGHT"]["ENABLED"])
            self.assertEqual(config["WORKFLOW"]["INSIGHT"]["STRATEGY"], "ai")
            self.assertEqual(config["WORKFLOW"]["INSIGHT"]["MODE"], "daily")
            self.assertEqual(config["WORKFLOW"]["INSIGHT"]["MAX_ITEMS"], 9)
            self.assertEqual(config["WORKFLOW"]["INSIGHT"]["LANGUAGE"], "Japanese")

            self.assertEqual(config["FILTER"]["METHOD"], "ai")
            self.assertEqual(config["FILTER"]["FREQUENCY_FILE"], "topics.txt")
            self.assertEqual(config["AI_ANALYSIS"]["STRATEGY"], "ai")
            self.assertEqual(config["AI_ANALYSIS"]["MAX_ITEMS"], 9)
            self.assertEqual(
                config["AI_ANALYSIS"]["PROMPT_FILE"],
                str((config_dir / "global_insight_prompt.txt").resolve()),
            )
            self.assertEqual(config["AI_ANALYSIS"]["RUNTIME_CACHE"]["TTL_SECONDS"], 60)
            self.assertFalse(config["AI_ANALYSIS"]["RUNTIME_CACHE"]["ENABLED"])
            self.assertEqual(
                config["AI_FILTER"]["PROMPT_FILE"],
                str((config_dir / "ai_filter" / "prompt.txt").resolve()),
            )
            self.assertEqual(config["AI_FILTER"]["EXTRA_PARAMS"], {"top_p": 0.9})
            self.assertEqual(config["AI_FILTER"]["RUNTIME_CACHE"]["MAX_ENTRIES"], 128)
            self.assertFalse(config["AI_FILTER"]["FALLBACK_TO_KEYWORD"])
            self.assertEqual(config["DISPLAY"]["REGION_ORDER"], ["hotlist", "new_items", "standalone", "insight"])
            self.assertTrue(config["DISPLAY"]["REGIONS"]["INSIGHT"])

            self.assertEqual(config["AI"]["MODEL"], "openai/base-model")
            self.assertEqual(config["AI_FILTER_MODEL"]["MODEL"], "openai/selection-model")
            self.assertEqual(config["AI_FILTER_MODEL"]["TIMEOUT"], 222)
            self.assertEqual(config["AI_FILTER_MODEL"]["PROVIDER_FAMILY"], "auto")
            self.assertEqual(config["AI_ANALYSIS_MODEL"]["API_KEY"], "insight-key")
            self.assertEqual(config["AI_ANALYSIS_MODEL"]["TEMPERATURE"], 0.8)


class FrequencyWordsPathTest(unittest.TestCase):
    def test_load_keyword_rule_set_resolves_custom_short_name_from_config_root(self):
        with workspace_tmpdir() as project:
            config_dir = project / "config"
            write_text(
                config_dir / "custom" / "keyword" / "weekly.txt",
                """
                [WORD_GROUPS]
                AI
                """,
            )

            rule_set = load_keyword_rule_set("weekly.txt", config_root=config_dir)

            self.assertEqual(len(rule_set.groups), 1)
            self.assertEqual(rule_set.groups[0].group_key, "AI")
            self.assertEqual(rule_set.filter_tokens, ())
            self.assertEqual(rule_set.global_filters, ())

    def test_resolve_ai_interests_path_uses_default_root_file(self):
        with workspace_tmpdir() as project:
            config_dir = project / "config"
            write_text(config_dir / "ai_interests.txt", "AI agents")

            path = resolve_ai_interests_path(
                "ai_interests.txt",
                config_root=config_dir,
            )

            self.assertEqual(path, config_dir / "ai_interests.txt")


if __name__ == "__main__":
    unittest.main()
