import unittest
from types import SimpleNamespace

from newspulse.ai.filter import AIFilter


class SplitFallbackFilter(AIFilter):
    def __init__(self):
        self.classify_system = ""
        self.classify_user = "COUNT={news_count}\n{news_list}"
        self.debug = False
        self.calls = []
        self.client = SimpleNamespace(chat=self._chat)

    def _chat(self, messages):
        user_content = messages[-1]["content"]
        lines = user_content.splitlines()
        count = int(lines[0].split("=", 1)[1])
        self.calls.append(count)
        if count > 1:
            raise RuntimeError("split me")

        news_id = int(lines[1].split('.', 1)[0])
        return f'[{{"id": {news_id}, "tag_id": 1, "score": 0.9}}]'


class AIFilterTest(unittest.TestCase):
    def test_classify_batch_splits_failed_batch_until_single_item(self):
        flt = SplitFallbackFilter()
        titles = [
            {"id": 1, "title": "a", "source": "s"},
            {"id": 2, "title": "b", "source": "s"},
            {"id": 3, "title": "c", "source": "s"},
            {"id": 4, "title": "d", "source": "s"},
        ]
        tags = [{"id": 1, "tag": "AI", "description": "AI news"}]

        results = flt.classify_batch(titles, tags)

        self.assertEqual([r["news_item_id"] for r in results], [1, 2, 3, 4])
        self.assertEqual(flt.calls[0], 4)
        self.assertIn(2, flt.calls)
        self.assertIn(1, flt.calls)


if __name__ == "__main__":
    unittest.main()
