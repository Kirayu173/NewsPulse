# coding=utf-8
"""Environment doctor command."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from newspulse import __version__
from newspulse.cli.common import resolve_data_dir
from newspulse.core.preflight import PreflightCheckResult, PreflightReport, run_preflight

_STATUS_ICONS = {
    "pass": "[PASS]",
    "warn": "[WARN]",
    "fail": "[FAIL]",
    "skip": "[SKIP]",
}


def render_doctor_report(report: PreflightReport) -> None:
    """Print the shared preflight report in doctor-friendly format."""

    print("=" * 60)
    print(f"NewsPulse v{__version__} 环境体检")
    print("=" * 60)
    for check in report.checks:
        _print_check(check)
    print("-" * 60)
    summary = f"体检结果: 通过 {report.pass_count} 项  警告 {report.warn_count} 项  失败 {report.fail_count} 项"
    if report.skip_count:
        summary += f"  跳过 {report.skip_count} 项"
    print(summary)
    print("=" * 60)
    if report.ok:
        print("体检通过。")
    else:
        print("体检未通过，请先修复失败项。")


def run_doctor(config_path: Optional[str] = None) -> bool:
    """Run the shared preflight checks and persist the doctor report."""

    report = run_preflight(config_path, mode="doctor")
    render_doctor_report(report)
    _save_doctor_report(report)
    return report.ok


def _print_check(check: PreflightCheckResult) -> None:
    icon = _STATUS_ICONS.get(check.status, "[INFO]")
    print(f"{icon} {check.item}: {check.detail}")
    if check.hint:
        print(f"   修复建议: {check.hint}")


def _save_doctor_report(report: PreflightReport) -> None:
    try:
        output_dir = (resolve_data_dir(report.config) if report.config else Path("output")) / "meta"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "doctor_report.json"
        output_path.write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"体检报告已保存: {output_path}")
    except Exception as exc:
        print(f"体检报告保存失败: {exc}")
