import shutil
import unittest
import uuid
from pathlib import Path

from newspulse.workflow.selection.audit import write_stage4_selection_audit


class SelectionAuditWriterTest(unittest.TestCase):
    def _create_workspace_tmpdir(self) -> Path:
        root = Path(".tmp-test") / "workflow-selection-audit"
        root.mkdir(parents=True, exist_ok=True)
        path = root / str(uuid.uuid4())
        path.mkdir(parents=True, exist_ok=False)
        return path

    def test_write_stage4_selection_audit_outputs_utf8_bom_markdown(self):
        tmpdir = self._create_workspace_tmpdir()
        try:
            (tmpdir / "stage4_snapshot.json").write_text(
                """
                {
                  "summary": {
                    "generated_at": "2026-04-19T00:34:20+08:00",
                    "keyword": {"total_candidates": 4, "qualified_count": 3},
                    "semantic": {"passed_count": 2, "rejected_count": 1, "skipped": false},
                    "llm": {"evaluated_count": 2, "kept_count": 1, "rejected_count": 1, "skipped": false},
                    "ai": {"qualified_count": 1}
                  },
                  "snapshot": {
                    "mode": "current",
                    "items": [],
                    "new_items": [],
                    "failed_sources": [
                      {"source_id": "github-trending-today"}
                    ],
                    "standalone_sections": []
                  }
                }
                """.strip(),
                encoding="utf-8-sig",
            )
            (tmpdir / "stage4_selection_keyword.json").write_text(
                """
                {
                  "selection": {
                    "qualified_items": [
                      {"news_item_id": "1", "source_id": "juejin", "current_rank": 1, "title": "AI 工具"}
                    ],
                    "rejected_items": [
                      {
                        "news_item_id": "9",
                        "source_id": "tencent-hot",
                        "current_rank": 9,
                        "title": "Sports news",
                        "rejected_stage": "rule",
                        "rejected_reason": "matched global blacklist: sports"
                      }
                    ]
                  }
                }
                """.strip(),
                encoding="utf-8-sig",
            )
            (tmpdir / "stage4_selection_ai.json").write_text(
                """
                {
                  "summary": {
                    "generated_at": "2026-04-19T00:34:20+08:00",
                    "keyword": {"total_candidates": 4, "qualified_count": 3},
                    "semantic": {"passed_count": 2, "rejected_count": 1, "skipped": false},
                    "llm": {"evaluated_count": 2, "kept_count": 1, "rejected_count": 1, "skipped": false},
                    "ai": {"qualified_count": 1}
                  },
                  "skipped": false,
                  "selection": {
                    "qualified_items": [
                      {"news_item_id": "1", "source_id": "juejin", "source_name": "掘金", "current_rank": 1, "title": "AI 工具"}
                    ],
                    "rejected_items": [
                      {
                        "news_item_id": "2",
                        "source_id": "tencent-hot",
                        "current_rank": 2,
                        "title": "腾讯新闻",
                        "rejected_stage": "llm",
                        "rejected_reason": "quality score below threshold 0.70"
                      }
                    ]
                  }
                }
                """.strip(),
                encoding="utf-8-sig",
            )
            (tmpdir / "stage4_selection_semantic.json").write_text(
                """
                {
                  "summary": {"generated_at": "2026-04-19T00:34:20+08:00"},
                  "semantic": {
                    "enabled": true,
                    "skipped": false,
                    "model": "openai/embedding-test",
                    "topic_count": 3,
                    "candidate_count": 6,
                    "passed_count": 2,
                    "rejected_count": 1,
                    "rejected_items": [
                      {
                        "news_item_id": "8",
                        "source_id": "wallstreetcn-hot",
                        "current_rank": 8,
                        "title": "Macro headline",
                        "rejected_stage": "semantic",
                        "rejected_reason": "semantic score below threshold 0.55"
                      }
                    ]
                  }
                }
                """.strip(),
                encoding="utf-8-sig",
            )
            (tmpdir / "stage4_selection_llm.json").write_text(
                """
                {
                  "summary": {"generated_at": "2026-04-19T00:34:20+08:00"},
                  "llm": {
                    "enabled": true,
                    "skipped": false,
                    "evaluated_count": 2,
                    "kept_count": 1,
                    "rejected_count": 1,
                    "rejected_items": [
                      {
                        "news_item_id": "2",
                        "source_id": "tencent-hot",
                        "current_rank": 2,
                        "title": "腾讯新闻",
                        "rejected_stage": "llm",
                        "rejected_reason": "quality score below threshold 0.70"
                      }
                    ]
                  }
                }
                """.strip(),
                encoding="utf-8-sig",
            )

            output_path = write_stage4_selection_audit(outbox_dir=tmpdir)
            data = output_path.read_bytes()
            text = output_path.read_text(encoding="utf-8-sig")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

        self.assertTrue(data.startswith(b"\xef\xbb\xbf"))
        self.assertIn("审阅文档", text)
        self.assertIn("漏斗概览", text)
        self.assertIn("LLM 层淘汰样本", text)
        self.assertIn("最终保留样本", text)
        self.assertIn("openai/embedding-test", text)
        self.assertIn("AI 工具", text)
        self.assertNotIn("????", text)


if __name__ == "__main__":
    unittest.main()
