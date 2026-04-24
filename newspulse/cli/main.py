# coding=utf-8
"""CLI entrypoint orchestration."""

from __future__ import annotations

import argparse
from typing import Sequence

from newspulse import __version__
from newspulse.cli.common import configure_console_output
from newspulse.cli.doctor import run_doctor
from newspulse.cli.errors import print_cli_error
from newspulse.cli.status import handle_status_commands
from newspulse.cli.test_notification import run_test_notification
from newspulse.cli.versioning import check_all_versions
from newspulse.core import load_config
from newspulse.core.preflight import run_preflight
from newspulse.runner import NewsRunner
from newspulse.utils.logging import configure_logging


def build_parser() -> argparse.ArgumentParser:
    """Build the root CLI parser."""

    parser = argparse.ArgumentParser(
        description="NewsPulse - hotlist aggregation and analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  run                Run the full NewsPulse workflow
  doctor             Run environment and config checks
  status             Show resolved scheduler status
  test-notification  Send a notification smoke test

Examples:
  newspulse run
  newspulse doctor
  newspulse status
  newspulse test-notification
  python -m newspulse
  python -m newspulse doctor
""",
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("run", help="run the full NewsPulse workflow")
    subparsers.add_parser("doctor", help="run environment and config checks")
    subparsers.add_parser("status", help="show resolved scheduler status")
    subparsers.add_parser("test-notification", help="send a notification smoke test")
    return parser

def main(argv: Sequence[str] | None = None) -> int:
    """Program entrypoint."""

    configure_console_output()
    configure_logging()
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    command = str(getattr(args, "command", "") or "run")
    debug_mode = False

    try:
        if command == "doctor":
            return 0 if run_doctor() else 1

        if command == "status":
            config = load_config()
            debug_mode = bool(config.get("DEBUG", False))
            handle_status_commands(config)
            return 0

        if command == "test-notification":
            config = load_config()
            debug_mode = bool(config.get("DEBUG", False))
            return 0 if run_test_notification(config) else 1

        return _run_workflow()
    except KeyboardInterrupt:
        print("已取消执行。")
        return 130
    except Exception as exc:
        if debug_mode:
            raise
        print_cli_error(exc)
        return 1


def _run_workflow() -> int:
    report = run_preflight(mode="startup")
    if not report.ok:
        _print_startup_failures(report)
        return 1

    if report.warn_count:
        _print_startup_warnings(report)

    config = report.config or load_config()
    version_url = config.get("VERSION_CHECK_URL", "")
    configs_version_url = config.get("CONFIGS_VERSION_CHECK_URL", "")

    need_update = False
    remote_version = None
    if version_url:
        need_update, remote_version = check_all_versions(
            version_url,
            configs_version_url,
        )

    runner = NewsRunner(config=config)
    if runner.is_github_actions and need_update and remote_version:
        runner.update_info = {
            "current_version": __version__,
            "remote_version": remote_version,
        }
    runner.run()
    return 0


def _print_startup_failures(report) -> None:
    print("启动预检未通过，已阻止执行。")
    for check in report.iter_status("fail"):
        print(f"- {check.item}: {check.detail}")
        if check.hint:
            print(f"  修复建议: {check.hint}")
    if report.warn_count:
        print("附加警告:")
        for check in report.iter_status("warn"):
            print(f"- {check.item}: {check.detail}")
            if check.hint:
                print(f"  修复建议: {check.hint}")
    print("可先运行 `newspulse doctor` 查看完整检查结果。")


def _print_startup_warnings(report) -> None:
    print("启动预检通过，但存在以下警告：")
    for check in report.iter_status("warn"):
        print(f"- {check.item}: {check.detail}")
        if check.hint:
            print(f"  修复建议: {check.hint}")
