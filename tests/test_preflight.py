import os
import shutil
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from newspulse.core.preflight import run_preflight
from tests.helpers.io import write_text

TEST_TMPDIR = Path(".tmp-test") / "preflight"
TEST_TMPDIR.mkdir(parents=True, exist_ok=True)


@contextmanager
def workspace_tmpdir():
    path = TEST_TMPDIR / uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _write_timeline(config_dir: Path) -> None:
    write_text(
        config_dir / "timeline.yaml",
        """
        presets:
          always_on:
            default:
              collect: true
              analyze: false
              push: false
              report_mode: current
              ai_mode: follow_report
              once:
                analyze: false
                push: false
            periods: {}
            day_plans:
              all_day:
                periods: []
            week_map:
              1: all_day
              2: all_day
              3: all_day
              4: all_day
              5: all_day
              6: all_day
              7: all_day
        custom:
          default:
            collect: true
            analyze: false
            push: false
            report_mode: current
            ai_mode: follow_report
            once:
              analyze: false
              push: false
          periods: {}
          day_plans:
            all_day:
              periods: []
          week_map:
            1: all_day
            2: all_day
            3: all_day
            4: all_day
            5: all_day
            6: all_day
            7: all_day
        """,
    )


def _write_common_files(config_dir: Path) -> None:
    write_text(config_dir / "frequency_words.txt", "[WORD_GROUPS]\nAI\n")
    write_text(config_dir / "ai_interests.txt", "AI agents and coding tools")
    write_text(config_dir / "ai_analysis_prompt.txt", "[user]\n{item_analyses_json}")
    write_text(config_dir / "ai_insight_item_prompt.txt", "[user]\n{title}")
    write_text(config_dir / "ai_filter" / "prompt.txt", "[user]\n{news_list}")
    write_text(config_dir / "ai_filter" / "extract_prompt.txt", "[user]\nextract")
    write_text(config_dir / "ai_filter" / "update_tags_prompt.txt", "[user]\nupdate")
    _write_timeline(config_dir)


def _write_config(
    config_dir: Path,
    *,
    output_dir: Path,
    selection_strategy: str = "keyword",
    semantic_enabled: bool = False,
    fallback_to_keyword: bool = True,
    notification_enabled: bool = False,
) -> Path:
    _write_common_files(config_dir)
    config_path = config_dir / "config.yaml"
    write_text(
        config_path,
        f"""
        app:
          timezone: Asia/Shanghai
        schedule:
          enabled: true
          preset: always_on
        platforms:
          enabled: false
          sources: []
        report:
          mode: current
          display_mode: keyword
          rank_threshold: 10
        notification:
          enabled: {"true" if notification_enabled else "false"}
        workflow:
          selection:
            strategy: {selection_strategy}
            frequency_file: frequency_words.txt
            ai:
              interests_file: ai_interests.txt
              fallback_to_keyword: {"true" if fallback_to_keyword else "false"}
            semantic:
              enabled: {"true" if semantic_enabled else "false"}
          insight:
            enabled: false
            strategy: noop
            mode: current
        ai:
          runtime:
            model: openai/base-model
            api_key: test-key
            api_base: https://example.com/v1
          operations:
            selection:
              model: openai/filter-model
              prompt_file: ai_filter/prompt.txt
              extract_prompt_file: ai_filter/extract_prompt.txt
              update_tags_prompt_file: ai_filter/update_tags_prompt.txt
            insight:
              model: openai/insight-model
              prompt_file: ai_analysis_prompt.txt
              item_prompt_file: ai_insight_item_prompt.txt
        storage:
          backend: local
          local:
            data_dir: {output_dir.as_posix()}
            retention_days: 7
        """,
    )
    return config_path


class PreflightTest(unittest.TestCase):
    def test_run_preflight_passes_with_valid_keyword_config(self):
        with workspace_tmpdir() as root:
            config_path = _write_config(
                root / "config",
                output_dir=root / "output",
            )

            with patch.dict(os.environ, {}, clear=True):
                report = run_preflight(str(config_path), mode="startup")

            self.assertTrue(report.ok)
            self.assertEqual(report.fail_count, 0)
            self.assertEqual(report.warn_count, 0)
            self.assertEqual(report.config_path, str(config_path.resolve()))
            self.assertEqual(
                next(check.status for check in report.checks if check.item == "Config file"),
                "pass",
            )
            self.assertEqual(
                next(check.status for check in report.checks if check.item == "Frequency words"),
                "pass",
            )
            self.assertEqual(
                next(check.status for check in report.checks if check.item == "AI selection runtime"),
                "skip",
            )

    def test_run_preflight_fails_when_config_file_is_missing(self):
        missing_path = Path("D:/does-not-exist/config.yaml")
        report = run_preflight(str(missing_path), mode="startup")

        self.assertFalse(report.ok)
        self.assertEqual(report.fail_count, 1)
        self.assertEqual(report.checks[1].item, "Config file")
        self.assertEqual(report.checks[1].status, "fail")

    def test_run_preflight_warns_when_semantic_embedding_model_is_missing(self):
        with workspace_tmpdir() as root:
            config_path = _write_config(
                root / "config",
                output_dir=root / "output",
                selection_strategy="ai",
                semantic_enabled=True,
                fallback_to_keyword=False,
            )

            with patch.dict(os.environ, {}, clear=True):
                report = run_preflight(str(config_path), mode="startup")

            self.assertTrue(report.ok)
            self.assertEqual(
                next(check.status for check in report.checks if check.item == "Semantic embedding"),
                "warn",
            )
            self.assertIn(
                "auto-skip",
                next(check.detail for check in report.checks if check.item == "Semantic embedding"),
            )

    def test_run_preflight_reports_resolved_ai_runtime_details(self):
        with workspace_tmpdir() as root:
            config_path = _write_config(
                root / "config",
                output_dir=root / "output",
                selection_strategy="ai",
            )

            with patch.dict(os.environ, {}, clear=True):
                report = run_preflight(str(config_path), mode="doctor")

            detail = next(check.detail for check in report.checks if check.item == "AI selection runtime")
            self.assertIn("provider_family=openai", detail)
            self.assertIn("model=openai/filter-model", detail)

    def test_run_preflight_warns_when_notification_channel_is_missing(self):
        with workspace_tmpdir() as root:
            config_path = _write_config(
                root / "config",
                output_dir=root / "output",
                notification_enabled=True,
            )

            with patch.dict(os.environ, {}, clear=True):
                report = run_preflight(str(config_path), mode="doctor")

            self.assertTrue(report.ok)
            self.assertEqual(report.fail_count, 0)
            self.assertEqual(
                next(check.status for check in report.checks if check.item == "Notification"),
                "warn",
            )


if __name__ == "__main__":
    unittest.main()
