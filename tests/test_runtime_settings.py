import unittest
from types import SimpleNamespace
from unittest.mock import patch

from newspulse.runtime import RuntimeProviders, build_runtime


class RuntimeSettingsTest(unittest.TestCase):
    def test_ai_runtime_configs_use_module_specific_entries(self):
        runtime = build_runtime(
            {
                "AI": {"MODEL": "openai/base", "TIMEOUT": 120},
                "AI_ANALYSIS_MODEL": {"MODEL": "openai/analysis", "TIMEOUT": 180},
                "AI_FILTER_MODEL": {"MODEL": "openai/filter", "TIMEOUT": 360},
            }
        )

        self.assertEqual(runtime.settings.insight.ai_runtime_config["MODEL"], "openai/analysis")
        self.assertEqual(runtime.settings.selection.ai_runtime_config["MODEL"], "openai/filter")
        self.assertEqual(runtime.settings.selection.ai_runtime_config["TIMEOUT"], 360)

    def test_ai_filter_embedding_model_config_uses_same_provider_runtime(self):
        runtime = build_runtime(
            {
                "AI_FILTER_MODEL": {
                    "MODEL": "openai/filter-model",
                    "API_KEY": "filter-key",
                    "API_BASE": "https://provider.example/v1",
                    "TIMEOUT": 480,
                }
            }
        )

        with patch.dict("os.environ", {"AI_EMBEDDING_MODEL": "embedding-3", "AI_EMBEDDING_PROVIDER_FAMILY": "openai"}, clear=False):
            config = runtime.settings.selection.embedding_runtime_config

        self.assertEqual(config["MODEL"], "openai/embedding-3")
        self.assertEqual(config["API_KEY"], "filter-key")
        self.assertEqual(config["API_BASE"], "https://provider.example/v1")
        self.assertEqual(config["TIMEOUT"], 480)
        self.assertEqual(config["PROVIDER_FAMILY"], "openai")

    def test_ai_filter_embedding_model_config_prefers_embedding_specific_credentials(self):
        runtime = build_runtime(
            {
                "AI_FILTER_MODEL": {
                    "MODEL": "anthropic/MiniMax-M2.7",
                    "API_KEY": "chat-key",
                    "API_BASE": "https://api.minimaxi.com/anthropic",
                    "PROVIDER_FAMILY": "anthropic",
                    "TIMEOUT": 240,
                }
            }
        )

        with patch.dict(
            "os.environ",
            {
                "AI_EMBEDDING_MODEL": "text-embedding-3-small",
                "AI_EMBEDDING_API_KEY": "embedding-key",
                "AI_EMBEDDING_BASE_URL": "https://embedding.example/v1",
                "AI_EMBEDDING_PROVIDER_FAMILY": "openai",
            },
            clear=False,
        ):
            config = runtime.settings.selection.embedding_runtime_config

        self.assertEqual(config["MODEL"], "openai/text-embedding-3-small")
        self.assertEqual(config["API_KEY"], "embedding-key")
        self.assertEqual(config["API_BASE"], "https://embedding.example/v1")
        self.assertEqual(config["PROVIDER_FAMILY"], "openai")

    def test_ai_filter_embedding_model_config_uses_openai_native_env_fallback(self):
        runtime = build_runtime(
            {
                "AI_FILTER_MODEL": {
                    "MODEL": "openai/filter-model",
                    "API_KEY": "",
                    "API_BASE": "",
                    "PROVIDER_FAMILY": "openai",
                    "TIMEOUT": 180,
                }
            }
        )

        with patch.dict(
            "os.environ",
            {
                "AI_EMBEDDING_MODEL": "text-embedding-3-small",
                "OPENAI_API_KEY": "openai-embedding-key",
                "OPENAI_BASE_URL": "https://embedding.example/v1",
            },
            clear=False,
        ):
            config = runtime.settings.selection.embedding_runtime_config

        self.assertEqual(config["MODEL"], "openai/text-embedding-3-small")
        self.assertEqual(config["API_KEY"], "openai-embedding-key")
        self.assertEqual(config["API_BASE"], "https://embedding.example/v1")
        self.assertEqual(config["PROVIDER_FAMILY"], "openai")

    def test_selection_builder_uses_loader_frequency_file(self):
        runtime = build_runtime(
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

        options = runtime.selection_builder.build()

        self.assertEqual(options.strategy, "ai")
        self.assertEqual(options.frequency_file, "topics.txt")
        self.assertEqual(options.ai.interests_file, "focus.txt")
        self.assertEqual(options.ai.batch_size, 3)
        self.assertEqual(options.ai.min_score, 0.75)
        self.assertFalse(options.ai.fallback_to_keyword)

    def test_selection_builder_prefers_workflow_selection_config(self):
        runtime = build_runtime(
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

        options = runtime.selection_builder.build()

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

    def test_insight_builder_honors_configured_strategy(self):
        runtime = build_runtime(
            {
                "AI_ANALYSIS": {
                    "ENABLED": True,
                    "STRATEGY": "noop",
                    "MODE": "follow_report",
                    "MAX_ITEMS": 6,
                }
            }
        )

        options = runtime.insight_builder.build(report_mode="daily")

        self.assertTrue(options.enabled)
        self.assertEqual(options.strategy, "noop")
        self.assertEqual(options.mode, "daily")
        self.assertEqual(options.max_items, 6)

    def test_insight_builder_prefers_workflow_insight_config(self):
        runtime = build_runtime(
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

        options = runtime.insight_builder.build(report_mode="daily")

        self.assertTrue(options.enabled)
        self.assertEqual(options.strategy, "ai")
        self.assertEqual(options.mode, "daily")
        self.assertTrue(options.metadata["mode_resolved_by_context"])
        self.assertEqual(options.max_items, 12)

    def test_region_order_filters_disabled_regions_even_if_region_order_lists_them(self):
        runtime = build_runtime(
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

        self.assertEqual(list(runtime.settings.render.region_order), ["hotlist", "standalone"])

    def test_runtime_settings_normalize_native_workflow_and_raw_ai_sections(self):
        runtime = build_runtime(
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

        settings = runtime.settings
        self.assertEqual(settings.selection.strategy, "ai")
        self.assertEqual(settings.selection.filter_config["PROMPT_FILE"], "selection_prompt.txt")
        self.assertEqual(settings.selection.filter_config["TIMEOUT"], 480)
        self.assertEqual(settings.selection.ai_runtime_config["MODEL"], "openai/selection-model")
        self.assertEqual(settings.selection.ai_runtime_config["API_KEY"], "base-key")
        self.assertEqual(settings.selection.ai_runtime_config["TIMEOUT"], 480)
        self.assertEqual(settings.selection.semantic.top_k, 6)
        self.assertEqual(settings.selection.semantic.direct_threshold, 0.82)

        self.assertEqual(settings.insight.analysis_config["PROMPT_FILE"], "insight_prompt.txt")
        self.assertEqual(settings.insight.analysis_config["MAX_ITEMS"], 8)
        self.assertTrue(settings.insight.analysis_config["CONTENT"]["ASYNC_ENABLED"])
        self.assertEqual(settings.insight.analysis_config["CONTENT"]["MAX_CONCURRENCY"], 5)
        self.assertEqual(settings.insight.analysis_config["CONTENT"]["REQUEST_TIMEOUT"], 18)
        self.assertEqual(settings.insight.ai_runtime_config["MODEL"], "openai/base")
        self.assertEqual(settings.insight.ai_runtime_config["API_KEY"], "insight-key")
        self.assertEqual(settings.insight.ai_runtime_config["TEMPERATURE"], 0.2)

    def test_runtime_settings_normalize_legacy_storage_and_platform_sections(self):
        runtime = build_runtime(
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

        settings = runtime.settings
        self.assertEqual(settings.storage.backend_type, "local")
        self.assertEqual(settings.storage.retention_days, 9)
        self.assertEqual(settings.storage.data_dir.as_posix(), "custom-output")
        self.assertFalse(settings.storage.enable_html)
        self.assertEqual([spec.source_id for spec in settings.crawler.crawl_source_specs], ["hackernews", "github-trending-today"])
        self.assertEqual(settings.crawler.platform_name_map["hackernews"], "Hacker News")

    def test_container_allows_provider_override(self):
        dummy_storage = SimpleNamespace(cleanup_old_data=lambda: None, cleanup=lambda: None)
        runtime = build_runtime(
            {"PLATFORMS": [], "DISPLAY": {"STANDALONE": {}}, "STORAGE": {"LOCAL": {"DATA_DIR": "output"}}},
            providers=RuntimeProviders(
                storage_factory=lambda settings: dummy_storage,
                snapshot_service_factory=lambda settings, storage: "snapshot-service",
            ),
        )

        self.assertIs(runtime.container.storage(), dummy_storage)
        self.assertEqual(runtime.container.snapshot_service(), "snapshot-service")


if __name__ == "__main__":
    unittest.main()
