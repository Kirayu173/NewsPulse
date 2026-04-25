from pathlib import Path
import unittest


class InsightPromptTemplateTest(unittest.TestCase):
    def test_aggregate_prompt_targets_lightweight_briefs(self):
        content = Path("config/ai_analysis_prompt.txt").read_text(encoding="utf-8")

        self.assertIn("lightweight insight briefs", content)
        self.assertIn("briefs_json", content)
        self.assertNotIn("item_analyses_json", content)
        self.assertIn("supporting_news_ids", content)
        self.assertIn("supporting_topics", content)


if __name__ == "__main__":
    unittest.main()
