import unittest

from newspulse.workflow.render.insight import render_insight_html_rich, render_insight_markdown
from newspulse.workflow.render.models import RenderInsightSectionView, RenderInsightView


class RenderInsightHelperTest(unittest.TestCase):
    def test_render_insight_helper_formats_shared_sections_for_html_and_markdown(self):
        insight = RenderInsightView(
            status="ok",
            sections=[
                RenderInsightSectionView(
                    key="core_trends",
                    title="核心趋势",
                    content="1. AI coding tools keep climbing. 2. Startup launches remain active.",
                ),
                RenderInsightSectionView(
                    key="signals",
                    title="关键信号",
                    content="OpenAI launches and Product Hunt launches keep appearing together.",
                ),
            ],
        )

        html = render_insight_html_rich(insight)
        markdown = render_insight_markdown(insight)

        self.assertIn("核心趋势", html)
        self.assertIn("AI coding tools keep climbing.", html)
        self.assertIn("<br>", html)
        self.assertIn("**AI 分析**", markdown)
        self.assertIn("**核心趋势**", markdown)
        self.assertIn("1. AI coding tools keep climbing.", markdown)
        self.assertIn("**关键信号**", markdown)

    def test_render_insight_helper_surfaces_skipped_and_error_messages(self):
        skipped = RenderInsightView(status="skipped", message="no selected items")
        errored = RenderInsightView(status="error", message="bad response")

        self.assertIn("跳过", render_insight_markdown(skipped))
        self.assertIn("no selected items", render_insight_markdown(skipped))
        self.assertIn("AI 分析失败", render_insight_markdown(errored))
        self.assertIn("bad response", render_insight_html_rich(errored))


if __name__ == "__main__":
    unittest.main()
