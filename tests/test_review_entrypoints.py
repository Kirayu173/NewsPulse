import os
import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from newspulse.crawler.models import CrawlBatchResult, SourceFetchResult
from newspulse.crawler.review import run_crawl_review
from newspulse.crawler.sources.base import SourceItem
from newspulse.storage.review import run_stage2_review
from newspulse.workflow.insight.review import run_insight_review
from newspulse.workflow.selection.review import run_selection_review
from newspulse.workflow.snapshot.review import run_snapshot_review
from tests.helpers.tempdir import WorkspaceTemporaryDirectory as TemporaryDirectory


class _FakeDataFetcher:
    def __init__(self, *args, **kwargs):
        pass

    def crawl(self, *args, **kwargs):
        return CrawlBatchResult(
            sources=[
                SourceFetchResult(
                    source_id="thepaper",
                    source_name="婢庢箖鏂伴椈",
                    resolved_source_id="thepaper",
                    items=[
                        SourceItem(
                            title="AI agents land in production",
                            url="https://example.com/a",
                            summary="A small but valid summary.",
                        )
                    ],
                    attempts=1,
                )
            ]
        )


class ReviewEntrypointSmokeTest(unittest.TestCase):
    def _create_config_workspace(self) -> tuple[TemporaryDirectory, Path]:
        tmp = TemporaryDirectory()
        root = Path(tmp.name)
        config_dir = root / "config"
        (config_dir / "rules" / "keyword").mkdir(parents=True, exist_ok=True)
        (config_dir / "profiles" / "ai").mkdir(parents=True, exist_ok=True)
        (config_dir / "prompts" / "selection").mkdir(parents=True, exist_ok=True)
        (config_dir / "prompts" / "insight").mkdir(parents=True, exist_ok=True)
        (config_dir / "config.yaml").write_text(
            """
            app:
              timezone: Asia/Shanghai
            schedule:
              enabled: false
              preset: always_on
            platforms:
              enabled: true
              sources:
                - id: thepaper
                  name: 婢庢箖鏂伴椈
            report:
              mode: current
              display_mode: keyword
              rank_threshold: 10
            notification:
              enabled: false
            workflow:
              selection:
                strategy: keyword
                priority_sort_enabled: false
                ai:
                  interests_file: profiles/ai/default.txt
                semantic:
                  enabled: true
              insight:
                enabled: false
                strategy: noop
                mode: current
            ai:
              runtime:
                model: openai/test-model
                api_key: ""
                api_base: ""
              operations:
                selection:
                  prompt_file: prompts/selection/classify.txt
                  extract_prompt_file: prompts/selection/extract_tags.txt
                  update_tags_prompt_file: prompts/selection/update_tags.txt
                insight:
                  prompt_file: prompts/insight/global_insight.txt
            storage:
              backend: local
              formats:
                txt: false
                html: false
              local:
                data_dir: output
                retention_days: 0
            advanced:
              crawler:
                request_interval: 0
            """,
            encoding="utf-8",
        )
        (config_dir / "rules/keyword/default.txt").write_text("[WORD_GROUPS]\nAI\n", encoding="utf-8")
        (config_dir / "profiles/ai/default.txt").write_text("AI agents", encoding="utf-8")
        (config_dir / "prompts/insight/global_insight.txt").write_text("[user]\n{item_summaries_json}\n{report_summary_json}", encoding="utf-8")
        (config_dir / "prompts" / "insight" / "item_summary_batch.txt").write_text("[user]\n{item_contexts_json}", encoding="utf-8")
        (config_dir / "prompts" / "insight" / "report_summary.txt").write_text("[user]\n{item_summaries_json}", encoding="utf-8")
        (config_dir / "prompts" / "selection" / "classify.txt").write_text("[user]\n{news_list}", encoding="utf-8")
        (config_dir / "prompts" / "selection" / "extract_tags.txt").write_text("[user]\nextract", encoding="utf-8")
        (config_dir / "prompts" / "selection" / "update_tags.txt").write_text("[user]\nupdate", encoding="utf-8")
        return tmp, config_dir / "config.yaml"

    def _create_outbox(self, label: str) -> Path:
        root = Path(".tmp-test") / label
        root.mkdir(parents=True, exist_ok=True)
        outbox = root / str(uuid.uuid4())
        outbox.mkdir(parents=True, exist_ok=False)
        return outbox

    def _assert_file(self, outbox: Path, name: str) -> None:
        self.assertTrue((outbox / name).exists(), name)

    def test_run_crawl_review_smoke(self):
        workspace, config_path = self._create_config_workspace()
        outbox = self._create_outbox("review-crawl-entry")
        try:
            with patch("newspulse.crawler.review.DataFetcher", _FakeDataFetcher):
                summary = run_crawl_review(config_path=config_path, outbox_dir=outbox)

            self.assertEqual(summary["success_count"], 1)
            self._assert_file(outbox, "crawl_review.md")
            self._assert_file(outbox, "crawl_batch.json")
        finally:
            workspace.cleanup()
            shutil.rmtree(outbox, ignore_errors=True)

    def test_run_stage2_review_smoke(self):
        workspace, config_path = self._create_config_workspace()
        outbox = self._create_outbox("review-stage2-entry")
        try:
            with patch("newspulse.storage.review.DataFetcher", _FakeDataFetcher):
                summary = run_stage2_review(config_path=config_path, outbox_dir=outbox)

            self.assertEqual(summary["normalized"]["total_items"], 1)
            self._assert_file(outbox, "stage2_review.md")
            self._assert_file(outbox, "stage2_latest_news_data.json")
        finally:
            workspace.cleanup()
            shutil.rmtree(outbox, ignore_errors=True)

    def test_run_snapshot_review_smoke(self):
        workspace, config_path = self._create_config_workspace()
        outbox = self._create_outbox("review-snapshot-entry")
        try:
            with patch("newspulse.workflow.snapshot.review.DataFetcher", _FakeDataFetcher):
                summary = run_snapshot_review(config_path=config_path, outbox_dir=outbox)

            self.assertIn("current", summary["snapshots"])
            self._assert_file(outbox, "stage3_snapshot_review.md")
            self._assert_file(outbox, "stage3_snapshot_current.json")
        finally:
            workspace.cleanup()
            shutil.rmtree(outbox, ignore_errors=True)

    def test_run_selection_review_smoke(self):
        workspace, config_path = self._create_config_workspace()
        outbox = self._create_outbox("review-selection-entry")
        try:
            with (
                patch("newspulse.workflow.selection.review.DataFetcher", _FakeDataFetcher),
                patch.dict(
                    os.environ,
                    {
                        "AI_API_KEY": "",
                        "API_KEY": "",
                        "OPENAI_API_KEY": "",
                        "ANTHROPIC_API_KEY": "",
                    },
                    clear=False,
                ),
            ):
                summary = run_selection_review(config_path=config_path, outbox_dir=outbox)

            self.assertEqual(summary["keyword"]["qualified_count"], 1)
            self.assertTrue(summary["ai"]["skipped"])
            self._assert_file(outbox, "stage4_selection_review.md")
            self._assert_file(outbox, "stage4_selection_ai.json")
        finally:
            workspace.cleanup()
            shutil.rmtree(outbox, ignore_errors=True)

    def test_run_insight_review_smoke(self):
        workspace, config_path = self._create_config_workspace()
        outbox = self._create_outbox("review-insight-entry")
        try:
            with patch("newspulse.workflow.insight.review.DataFetcher", _FakeDataFetcher):
                summary = run_insight_review(config_path=config_path, outbox_dir=outbox)

            self.assertFalse(summary["insight"]["enabled"])
            self._assert_file(outbox, "stage5_summary_review.md")
            self._assert_file(outbox, "stage5_global_insight_review.md")
            self._assert_file(outbox, "stage5_global_insight.json")
        finally:
            workspace.cleanup()
            shutil.rmtree(outbox, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
