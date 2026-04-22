import unittest

from newspulse.workflow.render.title_formatter import format_title_for_platform


class TitleFormatterTest(unittest.TestCase):
    def test_html_formatter_preserves_markup_structure_and_escapes_values(self):
        formatted = format_title_for_platform(
            "html",
            {
                "title": "A <B>",
                "source_name": "Hacker News",
                "time_display": "10:00",
                "count": 2,
                "ranks": [1, 2],
                "rank_threshold": 3,
                "url": "https://example.com?a=1&b=2",
                "mobile_url": "",
                "is_new": True,
                "matched_keyword": "AI",
            },
            show_source=True,
        )

        self.assertIn('<div class="new-title">', formatted)
        self.assertIn('class="source-tag">[Hacker News]</span>', formatted)
        self.assertIn('class="news-link">A &lt;B&gt;</a>', formatted)
        self.assertIn("<font color='green'>(2次)</font>", formatted)

    def test_telegram_formatter_uses_keyword_label_and_code_suffixes(self):
        formatted = format_title_for_platform(
            "telegram",
            {
                "title": "A <B>",
                "source_name": "Hacker News",
                "time_display": "10:00",
                "count": 2,
                "ranks": [1],
                "rank_threshold": 3,
                "url": "https://example.com?a=1&b=2",
                "mobile_url": "",
                "is_new": False,
                "matched_keyword": "AI",
            },
            show_source=False,
            show_keyword=True,
        )

        self.assertIn("<b>[AI]</b>", formatted)
        self.assertIn('<a href="https://example.com?a=1&amp;b=2">A &lt;B&gt;</a>', formatted)
        self.assertIn("<code>- 10:00</code>", formatted)
        self.assertIn("<code>(2次)</code>", formatted)


if __name__ == "__main__":
    unittest.main()
