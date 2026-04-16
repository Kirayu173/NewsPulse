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


if __name__ == "__main__":
    unittest.main()
