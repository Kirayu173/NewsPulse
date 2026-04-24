import unittest
from pathlib import Path
from tests.helpers.tempdir import WorkspaceTemporaryDirectory as TemporaryDirectory

from newspulse.workflow.shared.review_helpers import build_source_specs, write_review_text


class ReviewHelpersTest(unittest.TestCase):
    def test_write_review_text_uses_utf8_bom_encoding(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.md"
            write_review_text(path, "hello")

            self.assertTrue(path.read_bytes().startswith(b"\xef\xbb\xbf"))
            self.assertEqual(path.read_text(encoding="utf-8-sig"), "hello")

    def test_build_source_specs_filters_blank_ids(self):
        specs = build_source_specs(
            [
                {"id": "hackernews", "name": "Hacker News"},
                {"id": "", "name": "ignored"},
            ]
        )

        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0].source_id, "hackernews")


if __name__ == "__main__":
    unittest.main()
