import unittest
from unittest.mock import patch

from newspulse.context import AppContext


class AppContextTest(unittest.TestCase):
    def test_ai_runtime_configs_use_module_specific_entries(self):
        ctx = AppContext(
            {
                "AI": {"MODEL": "openai/base", "TIMEOUT": 120},
                "AI_ANALYSIS_MODEL": {"MODEL": "openai/analysis", "TIMEOUT": 180},
                "AI_TRANSLATION_MODEL": {"MODEL": "openai/translation", "TIMEOUT": 90},
                "AI_FILTER_MODEL": {"MODEL": "openai/filter", "TIMEOUT": 360},
            }
        )

        self.assertEqual(ctx.ai_analysis_model_config["MODEL"], "openai/analysis")
        self.assertEqual(ctx.ai_translation_model_config["MODEL"], "openai/translation")
        self.assertEqual(ctx.ai_filter_model_config["MODEL"], "openai/filter")
        self.assertEqual(ctx.ai_filter_model_config["TIMEOUT"], 360)

    def test_ai_filter_embedding_model_config_uses_same_provider_runtime(self):
        ctx = AppContext(
            {
                "AI_FILTER_MODEL": {
                    "MODEL": "openai/filter-model",
                    "API_KEY": "filter-key",
                    "API_BASE": "https://provider.example/v1",
                    "TIMEOUT": 480,
                }
            }
        )

        with patch.dict("os.environ", {"EMB_MODEL": "embedding-3"}, clear=False):
            config = ctx.ai_filter_embedding_model_config

        self.assertEqual(config["MODEL"], "openai/embedding-3")
        self.assertEqual(config["API_KEY"], "filter-key")
        self.assertEqual(config["API_BASE"], "https://provider.example/v1")
        self.assertEqual(config["TIMEOUT"], 480)

    def test_build_selection_options_uses_loader_frequency_file(self):
        ctx = AppContext(
            {
                "FILTER": {
                    "METHOD": "ai",
                    "FREQUENCY_FILE": "topics.txt",
                    "PRIORITY_SORT_ENABLED": True,
                },
                "AI_FILTER": {
                    "INTERESTS_FILE": "focus.txt",
                    "BATCH_SIZE": 3,
                    "BATCH_INTERVAL": 1,
                    "MIN_SCORE": 0.75,
                    "FALLBACK_TO_KEYWORD": False,
                },
            }
        )

        options = ctx.build_selection_options()

        self.assertEqual(options.strategy, "ai")
        self.assertEqual(options.frequency_file, "topics.txt")
        self.assertEqual(options.ai.interests_file, "focus.txt")
        self.assertEqual(options.ai.batch_size, 3)
        self.assertEqual(options.ai.min_score, 0.75)
        self.assertFalse(options.ai.fallback_to_keyword)

    def test_build_selection_options_prefers_workflow_selection_config(self):
        ctx = AppContext(
            {
                "WORKFLOW": {
                    "SELECTION": {
                        "STRATEGY": "ai",
                        "FREQUENCY_FILE": "workflow-topics.txt",
                        "PRIORITY_SORT_ENABLED": False,
                        "AI": {
                            "INTERESTS_FILE": "workflow-focus.txt",
                            "BATCH_SIZE": 9,
                            "BATCH_INTERVAL": 2,
                            "MIN_SCORE": 0.6,
                            "FALLBACK_TO_KEYWORD": True,
                        },
                        "SEMANTIC": {
                            "ENABLED": True,
                            "TOP_K": 5,
                            "MIN_SCORE": 0.63,
                            "DIRECT_THRESHOLD": 0.86,
                        },
                    }
                },
                "FILTER": {
                    "METHOD": "keyword",
                    "FREQUENCY_FILE": "legacy-topics.txt",
                    "PRIORITY_SORT_ENABLED": True,
                },
                "AI_FILTER": {
                    "INTERESTS_FILE": "legacy-focus.txt",
                    "BATCH_SIZE": 3,
                    "BATCH_INTERVAL": 1,
                    "MIN_SCORE": 0.75,
                    "FALLBACK_TO_KEYWORD": False,
                },
            }
        )

        options = ctx.build_selection_options()

        self.assertEqual(options.strategy, "ai")
        self.assertEqual(options.frequency_file, "workflow-topics.txt")
        self.assertEqual(options.ai.interests_file, "workflow-focus.txt")
        self.assertEqual(options.ai.batch_size, 9)
        self.assertEqual(options.ai.min_score, 0.6)
        self.assertFalse(options.priority_sort_enabled)
        self.assertTrue(options.ai.fallback_to_keyword)
        self.assertTrue(options.semantic.enabled)
        self.assertEqual(options.semantic.top_k, 5)
        self.assertEqual(options.semantic.min_score, 0.63)
        self.assertEqual(options.semantic.direct_threshold, 0.86)

    def test_build_insight_options_honors_configured_strategy(self):
        ctx = AppContext(
            {
                "AI_ANALYSIS": {
                    "ENABLED": True,
                    "STRATEGY": "noop",
                    "MODE": "follow_report",
                    "MAX_ITEMS": 6,
                }
            }
        )

        options = ctx.build_insight_options(report_mode="daily")

        self.assertTrue(options.enabled)
        self.assertEqual(options.strategy, "noop")
        self.assertEqual(options.mode, "daily")
        self.assertEqual(options.max_items, 6)

    def test_build_insight_options_prefers_workflow_insight_config(self):
        ctx = AppContext(
            {
                "WORKFLOW": {
                    "INSIGHT": {
                        "ENABLED": True,
                        "STRATEGY": "ai",
                        "MODE": "current",
                        "MAX_ITEMS": 12,
                    }
                },
                "AI_ANALYSIS": {
                    "ENABLED": True,
                    "STRATEGY": "noop",
                    "MODE": "follow_report",
                    "MAX_ITEMS": 6,
                },
            }
        )

        options = ctx.build_insight_options(report_mode="daily")

        self.assertTrue(options.enabled)
        self.assertEqual(options.strategy, "ai")
        self.assertEqual(options.mode, "daily")
        self.assertTrue(options.metadata["mode_resolved_by_context"])
        self.assertEqual(options.max_items, 12)

    def test_build_localization_options_supports_split_new_items_scope(self):
        ctx = AppContext(
            {
                "AI_TRANSLATION": {
                    "ENABLED": True,
                    "STRATEGY": "ai",
                    "LANGUAGE": "Japanese",
                    "SCOPE": {
                        "HOTLIST": False,
                        "NEW_ITEMS": True,
                        "STANDALONE": True,
                        "INSIGHT": True,
                    },
                }
            }
        )

        options = ctx.build_localization_options()

        self.assertTrue(options.enabled)
        self.assertEqual(options.strategy, "ai")
        self.assertEqual(options.language, "Japanese")
        self.assertFalse(options.scope.selection_titles)
        self.assertTrue(options.scope.new_items)
        self.assertTrue(options.scope.standalone)
        self.assertTrue(options.scope.insight_sections)

    def test_build_localization_options_prefers_workflow_localization_config(self):
        ctx = AppContext(
            {
                "WORKFLOW": {
                    "LOCALIZATION": {
                        "ENABLED": True,
                        "STRATEGY": "ai",
                        "LANGUAGE": "German",
                        "SCOPE": {
                            "SELECTION_TITLES": True,
                            "NEW_ITEMS": False,
                            "STANDALONE": False,
                            "INSIGHT_SECTIONS": True,
                        },
                    }
                },
                "AI_TRANSLATION": {
                    "ENABLED": True,
                    "STRATEGY": "ai",
                    "LANGUAGE": "Japanese",
                    "SCOPE": {
                        "HOTLIST": False,
                        "NEW_ITEMS": True,
                        "STANDALONE": True,
                        "INSIGHT": False,
                    },
                },
            }
        )

        options = ctx.build_localization_options()

        self.assertTrue(options.enabled)
        self.assertEqual(options.language, "German")
        self.assertTrue(options.scope.selection_titles)
        self.assertFalse(options.scope.new_items)
        self.assertFalse(options.scope.standalone)
        self.assertTrue(options.scope.insight_sections)

    def test_native_workflow_and_raw_ai_sections_drive_derived_stage_configs(self):
        ctx = AppContext(
            {
                "workflow": {
                    "selection": {
                        "strategy": "ai",
                        "frequency_file": "topics.txt",
                        "priority_sort_enabled": False,
                        "ai": {
                            "interests_file": "focus.txt",
                            "batch_size": 11,
                            "batch_interval": 1.5,
                            "min_score": 0.62,
                            "reclassify_threshold": 0.58,
                            "fallback_to_keyword": False,
                        },
                        "semantic": {
                            "enabled": True,
                            "top_k": 6,
                            "min_score": 0.6,
                            "direct_threshold": 0.82,
                        },
                    },
                    "insight": {
                        "enabled": True,
                        "strategy": "ai",
                        "mode": "current",
                        "max_items": 8,
                        "language": "Japanese",
                    },
                    "localization": {
                        "enabled": True,
                        "strategy": "ai",
                        "language": "German",
                        "scope": {
                            "selection_titles": True,
                            "new_items": False,
                            "standalone": True,
                            "insight_sections": True,
                        },
                    },
                },
                "ai": {
                    "runtime": {
                        "model": "openai/base",
                        "api_key": "base-key",
                        "timeout": 120,
                        "temperature": 0.5,
                    },
                    "operations": {
                        "selection": {
                            "model": "openai/selection-model",
                            "timeout": 480,
                            "num_retries": 0,
                            "prompt_file": "selection_prompt.txt",
                            "extract_prompt_file": "selection_extract.txt",
                            "update_tags_prompt_file": "selection_update.txt",
                        },
                        "insight": {
                            "api_key": "insight-key",
                            "temperature": 0.2,
                            "prompt_file": "insight_prompt.txt",
                        },
                        "localization": {
                            "api_base": "https://translation.example/v1",
                            "num_retries": 3,
                            "prompt_file": "translation_prompt.txt",
                            "extra_params": {"top_p": 0.9},
                        },
                    },
                },
                "FILTER": {"METHOD": "keyword"},
                "AI_FILTER": {"PROMPT_FILE": "legacy_selection_prompt.txt"},
                "AI_ANALYSIS": {"PROMPT_FILE": "legacy_insight_prompt.txt"},
                "AI_TRANSLATION": {"PROMPT_FILE": "legacy_translation_prompt.txt"},
            }
        )

        self.assertEqual(ctx.filter_method, "ai")
        self.assertEqual(ctx.ai_filter_config["PROMPT_FILE"], "selection_prompt.txt")
        self.assertEqual(ctx.ai_filter_config["TIMEOUT"], 480)
        self.assertEqual(ctx.ai_filter_model_config["MODEL"], "openai/selection-model")
        self.assertEqual(ctx.ai_filter_model_config["API_KEY"], "base-key")
        self.assertEqual(ctx.ai_filter_model_config["TIMEOUT"], 480)
        self.assertEqual(ctx.selection_stage_config["SEMANTIC"]["TOP_K"], 6)
        self.assertEqual(ctx.selection_stage_config["SEMANTIC"]["DIRECT_THRESHOLD"], 0.82)

        self.assertEqual(ctx.ai_analysis_config["PROMPT_FILE"], "insight_prompt.txt")
        self.assertEqual(ctx.ai_analysis_config["MAX_ITEMS"], 8)
        self.assertEqual(ctx.ai_analysis_model_config["MODEL"], "openai/base")
        self.assertEqual(ctx.ai_analysis_model_config["API_KEY"], "insight-key")
        self.assertEqual(ctx.ai_analysis_model_config["TEMPERATURE"], 0.2)

        self.assertEqual(ctx.ai_translation_config["PROMPT_FILE"], "translation_prompt.txt")
        self.assertEqual(ctx.ai_translation_config["NUM_RETRIES"], 3)
        self.assertEqual(ctx.ai_translation_config["EXTRA_PARAMS"], {"top_p": 0.9})
        self.assertEqual(ctx.ai_translation_model_config["API_BASE"], "https://translation.example/v1")
        self.assertEqual(ctx.ai_translation_model_config["NUM_RETRIES"], 3)

    def test_context_no_longer_exposes_legacy_report_helpers(self):
        self.assertFalse(hasattr(AppContext, "load_frequency_words"))
        self.assertFalse(hasattr(AppContext, "matches_word_groups"))
        self.assertFalse(hasattr(AppContext, "count_frequency"))
        self.assertFalse(hasattr(AppContext, "prepare_report"))
        self.assertFalse(hasattr(AppContext, "generate_html"))
        self.assertFalse(hasattr(AppContext, "render_html"))
        self.assertFalse(hasattr(AppContext, "split_content"))
        self.assertFalse(hasattr(AppContext, "create_notification_dispatcher"))
        self.assertFalse(hasattr(AppContext, "convert_selection_to_report_data"))


if __name__ == "__main__":
    unittest.main()
