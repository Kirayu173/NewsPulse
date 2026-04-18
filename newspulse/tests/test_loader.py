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
                    localization:
                      api_key: translation-key
                      temperature: 0.2
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
            self.assertEqual(config["AI_TRANSLATION_MODEL"]["API_KEY"], "translation-key")
            self.assertEqual(config["AI_TRANSLATION_MODEL"]["TEMPERATURE"], 0.2)
            self.assertEqual(config["AI_FILTER_MODEL"]["TIMEOUT"], 480)
            self.assertEqual(config["AI_FILTER_MODEL"]["NUM_RETRIES"], 0)
            self.assertEqual(config["AI_FILTER_MODEL"]["MAX_TOKENS"], 2000)
            self.assertEqual(config["AI"]["TIMEOUT"], 120)
            self.assertEqual(config["AI"]["NUM_RETRIES"], 1)

    def test_load_config_supports_workflow_stage_sections_and_ai_operations(self):
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            config_dir = workspace / "config"
            config_file = config_dir / "config.yaml"
            _write_text(config_dir / "ai_analysis_prompt.txt", "[user]\nanalysis")
            _write_text(config_dir / "ai_translation_prompt.txt", "[user]\ntranslate")
            _write_text(config_dir / "ai_filter" / "prompt.txt", "[user]\nfilter")
            _write_text(config_dir / "ai_filter" / "extract_prompt.txt", "[user]\nextract")
            _write_text(config_dir / "ai_filter" / "update_tags_prompt.txt", "[user]\nupdate")
            _write_text(
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
                  insight:
                    enabled: true
                    strategy: ai
                    mode: daily
                    max_items: 9
                    include_standalone: true
                    include_rank_timeline: true
                    language: Japanese
                  localization:
                    enabled: true
                    strategy: ai
                    language: English
                    scope:
                      selection_titles: false
                      new_items: true
                      standalone: false
                      insight_sections: true
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
                      extra_params:
                        top_p: 0.9
                    insight:
                      prompt_file: ai_analysis_prompt.txt
                      api_key: insight-key
                      temperature: 0.8
                    localization:
                      prompt_file: ai_translation_prompt.txt
                      api_base: https://translation.example/v1
                      num_retries: 0
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

            self.assertTrue(config["WORKFLOW"]["INSIGHT"]["ENABLED"])
            self.assertEqual(config["WORKFLOW"]["INSIGHT"]["STRATEGY"], "ai")
            self.assertEqual(config["WORKFLOW"]["INSIGHT"]["MODE"], "daily")
            self.assertEqual(config["WORKFLOW"]["INSIGHT"]["MAX_ITEMS"], 9)
            self.assertTrue(config["WORKFLOW"]["INSIGHT"]["INCLUDE_STANDALONE"])
            self.assertTrue(config["WORKFLOW"]["INSIGHT"]["INCLUDE_RANK_TIMELINE"])
            self.assertEqual(config["WORKFLOW"]["INSIGHT"]["LANGUAGE"], "Japanese")

            self.assertTrue(config["WORKFLOW"]["LOCALIZATION"]["ENABLED"])
            self.assertEqual(config["WORKFLOW"]["LOCALIZATION"]["STRATEGY"], "ai")
            self.assertEqual(config["WORKFLOW"]["LOCALIZATION"]["LANGUAGE"], "English")
            self.assertFalse(config["WORKFLOW"]["LOCALIZATION"]["SCOPE"]["SELECTION_TITLES"])
            self.assertTrue(config["WORKFLOW"]["LOCALIZATION"]["SCOPE"]["NEW_ITEMS"])
            self.assertFalse(config["WORKFLOW"]["LOCALIZATION"]["SCOPE"]["STANDALONE"])
            self.assertTrue(config["WORKFLOW"]["LOCALIZATION"]["SCOPE"]["INSIGHT_SECTIONS"])

            self.assertEqual(config["FILTER"]["METHOD"], "ai")
            self.assertEqual(config["FILTER"]["FREQUENCY_FILE"], "topics.txt")
            self.assertEqual(config["AI_ANALYSIS"]["STRATEGY"], "ai")
            self.assertEqual(config["AI_ANALYSIS"]["PROMPT_FILE"], str(config_dir / "ai_analysis_prompt.txt"))
            self.assertEqual(config["AI_TRANSLATION"]["STRATEGY"], "ai")
            self.assertEqual(config["AI_TRANSLATION"]["PROMPT_FILE"], str(config_dir / "ai_translation_prompt.txt"))
            self.assertFalse(config["AI_TRANSLATION"]["SCOPE"]["HOTLIST"])
            self.assertTrue(config["AI_TRANSLATION"]["SCOPE"]["NEW_ITEMS"])
            self.assertTrue(config["AI_TRANSLATION"]["SCOPE"]["INSIGHT"])
            self.assertEqual(config["AI_FILTER"]["PROMPT_FILE"], str(config_dir / "ai_filter" / "prompt.txt"))
            self.assertEqual(config["AI_FILTER"]["EXTRA_PARAMS"], {"top_p": 0.9})
            self.assertFalse(config["AI_FILTER"]["FALLBACK_TO_KEYWORD"])
            self.assertEqual(config["DISPLAY"]["REGION_ORDER"], ["hotlist", "new_items", "standalone", "insight"])
            self.assertTrue(config["DISPLAY"]["REGIONS"]["INSIGHT"])

            self.assertEqual(config["AI"]["MODEL"], "openai/base-model")
            self.assertEqual(config["AI_FILTER_MODEL"]["MODEL"], "openai/selection-model")
            self.assertEqual(config["AI_FILTER_MODEL"]["TIMEOUT"], 222)
            self.assertEqual(config["AI_ANALYSIS_MODEL"]["API_KEY"], "insight-key")
            self.assertEqual(config["AI_ANALYSIS_MODEL"]["TEMPERATURE"], 0.8)
            self.assertEqual(config["AI_TRANSLATION_MODEL"]["API_BASE"], "https://translation.example/v1")
            self.assertEqual(config["AI_TRANSLATION_MODEL"]["NUM_RETRIES"], 0)

    def test_load_config_prefers_workflow_stage_sections_over_legacy_stage_inputs(self):
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            config_dir = workspace / "config"
            config_file = config_dir / "config.yaml"
            _write_text(config_dir / "ai_analysis_prompt.txt", "[user]\nanalysis")
            _write_text(config_dir / "ai_translation_prompt.txt", "[user]\ntranslate")
            _write_text(config_dir / "ai_filter" / "prompt.txt", "[user]\nfilter")
            _write_text(config_dir / "ai_filter" / "extract_prompt.txt", "[user]\nextract")
            _write_text(config_dir / "ai_filter" / "update_tags_prompt.txt", "[user]\nupdate")
            _write_text(
                config_file,
                """
                app:
                  timezone: Asia/Shanghai
                schedule:
                  enabled: false
                  preset: always_on
                workflow:
                  selection:
                    strategy: keyword
                    priority_sort_enabled: false
                    ai:
                      interests_file: workflow.txt
                      batch_size: 7
                  insight:
                    enabled: false
                    strategy: noop
                    mode: daily
                    max_items: 3
                    include_standalone: false
                    include_rank_timeline: false
                    language: Japanese
                  localization:
                    enabled: false
                    strategy: noop
                    language: English
                    scope:
                      selection_titles: true
                      new_items: true
                      standalone: false
                      insight_sections: false
                ai:
                  runtime:
                    model: openai/base-model
                  operations:
                    selection:
                      prompt_file: ai_filter/prompt.txt
                      extract_prompt_file: ai_filter/extract_prompt.txt
                      update_tags_prompt_file: ai_filter/update_tags_prompt.txt
                    insight:
                      prompt_file: ai_analysis_prompt.txt
                    localization:
                      prompt_file: ai_translation_prompt.txt
                filter:
                  method: ai
                  priority_sort_enabled: true
                ai_filter:
                  interests_file: ai.txt
                  batch_size: 12
                  batch_interval: 3
                  min_score: 0.7
                ai_analysis:
                  enabled: true
                  mode: current
                  max_news_for_analysis: 4
                  include_standalone: true
                  include_rank_timeline: false
                  language: Chinese
                  prompt_file: ai_analysis_prompt.txt
                ai_translation:
                  enabled: true
                  language: German
                  prompt_file: ai_translation_prompt.txt
                  scope:
                    hotlist: false
                    standalone: true
                    insight: true
                """,
            )

            with patch.dict(os.environ, {}, clear=True):
                config = load_config(str(config_file))

            self.assertEqual(config["WORKFLOW"]["SELECTION"]["STRATEGY"], "keyword")
            self.assertFalse(config["WORKFLOW"]["SELECTION"]["PRIORITY_SORT_ENABLED"])
            self.assertEqual(config["WORKFLOW"]["SELECTION"]["AI"]["INTERESTS_FILE"], "workflow.txt")
            self.assertEqual(config["WORKFLOW"]["SELECTION"]["AI"]["BATCH_SIZE"], 7)
            self.assertFalse(config["WORKFLOW"]["INSIGHT"]["ENABLED"])
            self.assertEqual(config["WORKFLOW"]["INSIGHT"]["STRATEGY"], "noop")
            self.assertEqual(config["WORKFLOW"]["INSIGHT"]["MODE"], "daily")
            self.assertEqual(config["WORKFLOW"]["INSIGHT"]["MAX_ITEMS"], 3)
            self.assertEqual(config["WORKFLOW"]["LOCALIZATION"]["LANGUAGE"], "English")
            self.assertTrue(config["WORKFLOW"]["LOCALIZATION"]["SCOPE"]["SELECTION_TITLES"])
            self.assertTrue(config["WORKFLOW"]["LOCALIZATION"]["SCOPE"]["NEW_ITEMS"])
            self.assertFalse(config["WORKFLOW"]["LOCALIZATION"]["SCOPE"]["STANDALONE"])
            self.assertFalse(config["WORKFLOW"]["LOCALIZATION"]["SCOPE"]["INSIGHT_SECTIONS"])

            self.assertEqual(config["FILTER"]["METHOD"], "keyword")
            self.assertEqual(config["AI_ANALYSIS"]["STRATEGY"], "noop")
            self.assertEqual(config["AI_TRANSLATION"]["STRATEGY"], "noop")


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
