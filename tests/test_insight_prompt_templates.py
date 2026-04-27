import unittest
from pathlib import Path


class InsightPromptTemplateTest(unittest.TestCase):
    def test_aggregate_prompt_targets_item_and_report_summaries(self):
        content = Path("config/prompts/insight/global_insight.txt").read_text(encoding="utf-8")

        self.assertIn("item summaries", content)
        self.assertIn("item_summaries_json", content)
        self.assertIn("report_summary_json", content)
        self.assertNotIn("theme_summaries_json", content)
        self.assertNotIn("briefs" + "_json", content)
        self.assertNotIn("item_" + "analyses_json", content)
        self.assertIn("supporting_news_ids", content)
        self.assertIn("supporting_topics", content)

    def test_item_and_report_prompt_templates_exist(self):
        item_prompt = Path("config/prompts/insight/item_summary_batch.txt").read_text(encoding="utf-8")
        report_prompt = Path("config/prompts/insight/report_summary.txt").read_text(encoding="utf-8")

        self.assertIn("item_contexts_json", item_prompt)
        self.assertIn("item_summaries_json", report_prompt)
        self.assertNotIn("theme_summaries_json", item_prompt + report_prompt)


if __name__ == "__main__":
    unittest.main()
