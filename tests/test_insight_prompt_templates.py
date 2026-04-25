from pathlib import Path
import unittest


class InsightPromptTemplateTest(unittest.TestCase):
    def test_aggregate_prompt_targets_theme_summaries(self):
        content = Path("config/global_insight_prompt.txt").read_text(encoding="utf-8")

        self.assertIn("主题摘要", content)
        self.assertIn("theme_summaries_json", content)
        self.assertIn("report_summary_json", content)
        self.assertNotIn("briefs" + "_json", content)
        self.assertNotIn("item_" + "analyses_json", content)
        self.assertIn("supporting_news_ids", content)
        self.assertIn("supporting_topics", content)


if __name__ == "__main__":
    unittest.main()
