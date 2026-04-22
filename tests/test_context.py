import unittest
from pathlib import Path
from unittest.mock import patch

from newspulse.context import AppContext, ServiceFactory


class AppContextTest(unittest.TestCase):
    def test_ai_runtime_configs_use_module_specific_entries(self):
        ctx = AppContext(
            {
                "AI": {"MODEL": "openai/base", "TIMEOUT": 120},
                "AI_ANALYSIS_MODEL": {"MODEL": "openai/analysis", "TIMEOUT": 180},
                "AI_FILTER_MODEL": {"MODEL": "openai/filter", "TIMEOUT": 360},
            }
        )

        self.assertEqual(ctx.ai_analysis_model_config["MODEL"], "openai/analysis")
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

    def test_region_order_filters_disabled_regions_even_if_region_order_lists_them(self):
        ctx = AppContext(
            {
                "DISPLAY": {
                    "REGION_ORDER": ["hotlist", "new_items", "standalone", "insight"],
                    "REGIONS": {
                        "HOTLIST": True,
                        "NEW_ITEMS": False,
                        "STANDALONE": True,
                        "INSIGHT": False,
                    },
                }
            }
        )

        self.assertEqual(ctx.region_order, ["hotlist", "standalone"])

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
                        "content": {
                            "async_enabled": True,
                            "max_concurrency": 5,
                            "request_timeout": 18,
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
                    },
                },
                "FILTER": {"METHOD": "keyword"},
                "AI_FILTER": {"PROMPT_FILE": "legacy_selection_prompt.txt"},
                "AI_ANALYSIS": {"PROMPT_FILE": "legacy_insight_prompt.txt"},
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
        self.assertTrue(ctx.ai_analysis_config["CONTENT"]["ASYNC_ENABLED"])
        self.assertEqual(ctx.ai_analysis_config["CONTENT"]["MAX_CONCURRENCY"], 5)
        self.assertEqual(ctx.ai_analysis_config["CONTENT"]["REQUEST_TIMEOUT"], 18)
        self.assertEqual(ctx.ai_analysis_model_config["MODEL"], "openai/base")
        self.assertEqual(ctx.ai_analysis_model_config["API_KEY"], "insight-key")
        self.assertEqual(ctx.ai_analysis_model_config["TEMPERATURE"], 0.2)

    def test_context_no_longer_exposes_removed_localization_or_legacy_report_helpers(self):
        self.assertFalse(hasattr(AppContext, "build_localization_options"))
        self.assertFalse(hasattr(AppContext, "create_localization_service"))
        self.assertFalse(hasattr(AppContext, "run_localization_stage"))
        self.assertFalse(hasattr(AppContext, "load_frequency_words"))
        self.assertFalse(hasattr(AppContext, "matches_word_groups"))
        self.assertFalse(hasattr(AppContext, "count_frequency"))
        self.assertFalse(hasattr(AppContext, "prepare_report"))
        self.assertFalse(hasattr(AppContext, "generate_html"))
        self.assertFalse(hasattr(AppContext, "render_html"))
        self.assertFalse(hasattr(AppContext, "split_content"))
        self.assertFalse(hasattr(AppContext, "create_notification_dispatcher"))
        self.assertFalse(hasattr(AppContext, "convert_selection_to_report_data"))

    def test_context_normalizes_legacy_storage_and_platform_sections(self):
        ctx = AppContext(
            {
                "storage": {
                    "formats": {"html": False, "txt": True},
                    "local": {"data_dir": "custom-output", "retention_days": 9},
                },
                "platforms": {
                    "sources": [
                        {"id": "hackernews", "name": "Hacker News"},
                        {"id": "github-trending-today", "name": ""},
                    ]
                },
            }
        )

        self.assertEqual(ctx.storage_backend_type, "local")
        self.assertEqual(ctx.storage_retention_days, 9)
        self.assertEqual(ctx.get_data_dir(), Path("custom-output"))
        self.assertFalse(ctx.storage_formats["HTML"])
        self.assertEqual([spec.source_id for spec in ctx.crawl_source_specs], ["hackernews", "github-trending-today"])
        self.assertEqual(ctx.platform_name_map["hackernews"], "Hacker News")

    def test_create_service_methods_delegate_to_service_factory(self):
        with patch.object(ServiceFactory, "create_snapshot_service", return_value="snapshot-service") as mocked:
            ctx = AppContext({"PLATFORMS": [], "DISPLAY": {"STANDALONE": {}}, "STORAGE": {"LOCAL": {"DATA_DIR": "output"}}})

            self.assertIsInstance(ctx.service_factory, ServiceFactory)
            self.assertIs(ctx.service_factory, ctx.service_factory)
            self.assertEqual(ctx.create_snapshot_service(), "snapshot-service")

        mocked.assert_called_once()


if __name__ == "__main__":
    unittest.main()
