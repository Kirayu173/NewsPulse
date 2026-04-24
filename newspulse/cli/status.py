# coding=utf-8
"""Status display command."""

from typing import Dict

from newspulse import __version__
from newspulse.runtime import build_runtime


def handle_status_commands(config: Dict) -> None:
    """处理状态查看命令并显示当前调度状态。"""
    runtime = build_runtime(config)
    settings = runtime.settings

    try:
        print("=" * 60)
        print(f"NewsPulse v{__version__} 调度状态")
        print("=" * 60)

        scheduler = runtime.container.scheduler()
        schedule = scheduler.resolve()

        now = settings.get_time()
        date_str = settings.format_date()

        print(f"\n当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')} ({settings.app.timezone})")
        print(f"当前日期: {date_str}")

        print("\n调度信息:")
        print(f"  日计划: {schedule.day_plan}")
        if schedule.period_key:
            print(f"  当前时间段: {schedule.period_name or schedule.period_key} ({schedule.period_key})")
        else:
            print("  当前时间段: 无（使用默认配置）")

        print("\n行为开关:")
        print(f"  采集数据: {'是' if schedule.collect else '否'}")
        print(f"  AI 分析:  {'是' if schedule.analyze else '否'}")
        print(f"  推送通知: {'是' if schedule.push else '否'}")
        print(f"  报告模式: {schedule.report_mode}")
        print(f"  AI 模式:  {schedule.ai_mode}")

        if schedule.period_key:
            print("\n一次性控制:")
            if schedule.once_analyze:
                already_analyzed = scheduler.already_executed(schedule.period_key, "analyze", date_str)
                print(f"  AI 分析:  仅一次 {'(今日已执行)' if already_analyzed else '(今日未执行)'}")
            else:
                print("  AI 分析:  不限次数")
            if schedule.once_push:
                already_pushed = scheduler.already_executed(schedule.period_key, "push", date_str)
                print(f"  推送通知: 仅一次 {'(今日已执行)' if already_pushed else '(今日未执行)'}")
            else:
                print("  推送通知: 不限次数")
        print("\n" + "=" * 60)
    finally:
        runtime.cleanup()
