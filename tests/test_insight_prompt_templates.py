from pathlib import Path
import unittest


class InsightPromptTemplateTest(unittest.TestCase):
    def test_item_prompt_keeps_fact_and_signal_boundaries(self):
        content = Path("config/ai_insight_item_prompt.txt").read_text(encoding="utf-8")

        self.assertIn("matched_topics", content)
        self.assertIn("selection_reasons", content)
        self.assertIn("严格区分“事实”和“信号/判断”", content)
        self.assertIn("不要把推测写进事实段落", content)
        self.assertIn("{evidence_sentences}", content)
        self.assertIn("{reduced_content}", content)

    def test_aggregate_prompt_uses_dynamic_sections_and_fixed_titles(self):
        content = Path("config/ai_analysis_prompt.txt").read_text(encoding="utf-8")

        self.assertIn("2~4 个最有把握的 section", content)
        self.assertIn("固定 title 映射", content)
        self.assertIn("`core_trends` -> `核心趋势`", content)
        self.assertIn("`signals` -> `关键信号`", content)
        self.assertIn('"title": "核心趋势"', content)
        self.assertIn('"title": "关键信号"', content)


if __name__ == "__main__":
    unittest.main()
