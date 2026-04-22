# coding=utf-8
"""Environment doctor command."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from newspulse import __version__
from newspulse.cli.common import resolve_data_dir
from newspulse.context import AppContext
from newspulse.core import load_config, parse_multi_account_config
from newspulse.core.config_paths import (
    get_config_layout,
    resolve_frequency_words_path,
    resolve_timeline_path,
)


def _record_doctor_result(results: List[Tuple[str, str, str]], status: str, item: str, detail: str) -> None:
    """记录并打印 doctor 检查结果"""
    icon_map = {
        "pass": "✅",
        "warn": "⚠️",
        "fail": "❌",
    }
    icon = icon_map.get(status, "•")
    results.append((status, item, detail))
    print(f"{icon} {item}: {detail}")

def _save_doctor_report(
    results: List[Tuple[str, str, str]],
    pass_count: int,
    warn_count: int,
    fail_count: int,
    config_path: Optional[str],
    data_dir: Optional[Path] = None,
) -> None:
    """保存 doctor 体检报告到 JSON 文件"""
    report = {
        "version": __version__,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config_path": config_path or str(get_config_layout().config_path),
        "summary": {
            "pass": pass_count,
            "warn": warn_count,
            "fail": fail_count,
            "ok": fail_count == 0,
        },
        "checks": [
            {"status": status, "item": item, "detail": detail}
            for status, item, detail in results
        ],
    }

    try:
        output_dir = (data_dir or Path("output")) / "meta"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "doctor_report.json"
        output_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"体检报告已保存: {output_path}")
    except Exception as e:
        print(f"⚠️ 体检报告保存失败: {e}")

def run_doctor(config_path: Optional[str] = None) -> bool:
    """运行环境体检"""
    print("=" * 60)
    print(f"NewsPulse v{__version__} 环境体检")
    print("=" * 60)

    results: List[Tuple[str, str, str]] = []
    config = None

    # 1) Python 版本检查
    py_ok = sys.version_info >= (3, 10)
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if py_ok:
        _record_doctor_result(results, "pass", "Python版本", f"{py_version} (满足 >= 3.10)")
    else:
        _record_doctor_result(results, "fail", "Python版本", f"{py_version} (不满足 >= 3.10)")

    # 2) 关键文件检查
    layout = get_config_layout(config_path)
    resolved_config_path = str(layout.config_path)
    frequency_path = str(resolve_frequency_words_path(config_root=layout.config_root))
    timeline_path = str(resolve_timeline_path(config_root=layout.config_root))

    required_files = [
        (resolved_config_path, "Config file"),
        (frequency_path, "Frequency words"),
    ]
    optional_files = [
        (timeline_path, "Timeline file"),
    ]

    for path_str, desc in required_files:
        if Path(path_str).exists():
            _record_doctor_result(results, "pass", desc, f"已找到: {path_str}")
        else:
            _record_doctor_result(results, "fail", desc, f"缺失: {path_str}")

    for path_str, desc in optional_files:
        if Path(path_str).exists():
            _record_doctor_result(results, "pass", desc, f"已找到: {path_str}")
        else:
            _record_doctor_result(results, "warn", desc, f"未找到: {path_str}（将使用默认调度模板）")

    # 3) 配置加载检查
    try:
        config = load_config(config_path)
        _record_doctor_result(results, "pass", "Config load", f"loaded: {resolved_config_path}")
    except Exception as e:
        _record_doctor_result(results, "fail", "配置加载", f"加载失败: {e}")

    # 后续检查依赖配置对象
    if config:
        # 4) 调度配置检查
        try:
            ctx = AppContext(config)
            schedule = ctx.create_scheduler().resolve()
            detail = f"调度解析成功（report_mode={schedule.report_mode}, ai_mode={schedule.ai_mode}）"
            _record_doctor_result(results, "pass", "调度配置", detail)
        except Exception as e:
            _record_doctor_result(results, "fail", "调度配置", f"解析失败: {e}")

        # 5) AI 配置检查（按功能场景区分严重级别）
        ai_analysis_enabled = config.get("AI_ANALYSIS", {}).get("ENABLED", False)
        ai_filter_enabled = config.get("FILTER", {}).get("METHOD", "keyword") == "ai"
        ai_enabled = ai_analysis_enabled or ai_filter_enabled

        if ai_enabled:
            try:
                from newspulse.workflow.shared.ai_runtime.client import AIRuntimeClient
                ai_targets = []
                if ai_analysis_enabled:
                    ai_targets.append(("analysis", config.get("AI_ANALYSIS_MODEL", {}), "fail"))
                if ai_filter_enabled:
                    ai_targets.append(("filter", config.get("AI_FILTER_MODEL", {}), "warn"))

                status = "pass"
                details = []
                for label, ai_runtime_config, invalid_status in ai_targets:
                    valid, message = AIRuntimeClient(ai_runtime_config).validate_config()
                    if valid:
                        details.append(f"{label}: {ai_runtime_config.get('MODEL', '')}")
                        continue

                    details.append(f"{label}: {message}")
                    if invalid_status == "fail":
                        status = "fail"
                    elif status != "fail":
                        status = "warn"

                _record_doctor_result(results, status, "AI配置", "；".join(details))
            except Exception as e:
                _record_doctor_result(results, "fail", "AI配置", f"校验异常: {e}")
        else:
            _record_doctor_result(results, "warn", "AI配置", "未启用 AI 功能，跳过校验")

        # 6) 存储配置检查
        try:
            sm = AppContext(config).get_storage_manager()
            retention_days = config.get("STORAGE", {}).get("LOCAL", {}).get("RETENTION_DAYS", 0)
            detail = f"当前后端: {sm.backend_name}"
            if retention_days > 0:
                detail += f"；保留天数: {retention_days} 天"
            _record_doctor_result(results, "pass", "存储配置", detail)
        except Exception as e:
            _record_doctor_result(results, "fail", "存储配置", f"检查失败: {e}")

        # 7) 通知渠道配置检查
        channel_details = []
        channel_issues = []
        max_accounts = config.get("MAX_ACCOUNTS_PER_CHANNEL", 3)

        generic_urls = parse_multi_account_config(config.get("GENERIC_WEBHOOK_URL", ""))
        if generic_urls:
            channel_details.append(f"通用Webhook({min(len(generic_urls), max_accounts)}个)")

        if channel_issues and not channel_details:
            _record_doctor_result(results, "fail", "通知配置", "；".join(channel_issues))
        elif channel_issues and channel_details:
            detail = f"可用渠道: {', '.join(channel_details)}；问题: {'；'.join(channel_issues)}"
            _record_doctor_result(results, "warn", "通知配置", detail)
        elif channel_details:
            _record_doctor_result(results, "pass", "通知配置", f"可用渠道: {', '.join(channel_details)}")
        else:
            _record_doctor_result(results, "warn", "通知配置", "未配置任何通知渠道")

        # 8) 输出目录可写检查
        try:
            output_dir = resolve_data_dir(config)
            output_dir.mkdir(parents=True, exist_ok=True)
            probe_file = output_dir / ".doctor_write_probe"
            probe_file.write_text("ok", encoding="utf-8")
            probe_file.unlink(missing_ok=True)
            _record_doctor_result(results, "pass", "输出目录", f"可写: {output_dir}")
        except Exception as e:
            _record_doctor_result(results, "fail", "输出目录", f"不可写: {e}")

    pass_count = sum(1 for status, _, _ in results if status == "pass")
    warn_count = sum(1 for status, _, _ in results if status == "warn")
    fail_count = sum(1 for status, _, _ in results if status == "fail")

    _save_doctor_report(
        results,
        pass_count,
        warn_count,
        fail_count,
        resolved_config_path,
        data_dir=resolve_data_dir(config),
    )

    print("-" * 60)
    print(f"体检结果: ✅ {pass_count} 项通过  ⚠️ {warn_count} 项警告  ❌ {fail_count} 项失败")
    print("=" * 60)

    if fail_count == 0:
        print("体检通过。")
        return True

    print("体检未通过，请先修复失败项。")
    return False
