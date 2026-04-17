import unittest

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

    def test_build_insight_options_honors_configured_strategy(self):
        ctx = AppContext(
            {
                "AI_ANALYSIS": {
                    "ENABLED": True,
                    "STRATEGY": "noop",
                    "MODE": "follow_report",
                    "MAX_NEWS_FOR_ANALYSIS": 6,
                    "INCLUDE_STANDALONE": True,
                    "INCLUDE_RANK_TIMELINE": False,
                }
            }
        )

        options = ctx.build_insight_options(report_mode="daily")

        self.assertTrue(options.enabled)
        self.assertEqual(options.strategy, "noop")
        self.assertEqual(options.mode, "daily")
        self.assertEqual(options.max_items, 6)
        self.assertTrue(options.include_standalone)
        self.assertFalse(options.include_rank_timeline)

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

    def test_context_no_longer_exposes_legacy_report_helpers(self):
        self.assertFalse(hasattr(AppContext, "load_frequency_words"))
        self.assertFalse(hasattr(AppContext, "matches_word_groups"))
        self.assertFalse(hasattr(AppContext, "count_frequency"))
        self.assertFalse(hasattr(AppContext, "prepare_report"))
        self.assertFalse(hasattr(AppContext, "generate_html"))
        self.assertFalse(hasattr(AppContext, "render_html"))
        self.assertFalse(hasattr(AppContext, "split_content"))
        self.assertFalse(hasattr(AppContext, "create_notification_dispatcher"))


if __name__ == "__main__":
    unittest.main()
