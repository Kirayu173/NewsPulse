# coding=utf-8
"""Notification smoke-test command."""

from __future__ import annotations

import copy
from typing import Dict

from newspulse.context import AppContext
from newspulse.workflow.shared.contracts import (
    HotlistItem,
    ReportContent,
    ReportIntegrity,
    ReportPackage,
    ReportPackageMeta,
    SelectionGroup,
)


def _build_test_package(ctx: AppContext) -> ReportPackage:
    now = ctx.get_time()
    current_time = now.strftime("%Y-%m-%d %H:%M:%S")
    item = HotlistItem(
        news_item_id="notification-smoke-test",
        source_id="newspulse",
        source_name="NewsPulse",
        title=f"NewsPulse 通知测试 {current_time}",
        current_rank=1,
        ranks=[1],
        first_time=current_time,
        last_time=current_time,
        count=1,
        is_new=True,
    )
    group = SelectionGroup(
        key="notification_test",
        label="通知测试",
        items=[item],
        position=0,
    )
    return ReportPackage(
        meta=ReportPackageMeta(
            mode="daily",
            generated_at=current_time,
            report_type="通知测试报告",
            timezone=ctx.timezone,
            display_mode=ctx.display_mode,
            selection_strategy="keyword",
            insight_strategy="noop",
        ),
        content=ReportContent(
            hotlist_groups=[group],
            selected_items=[item],
            new_items=[item],
            standalone_sections=[],
            insight_sections=[],
        ),
        integrity=ReportIntegrity(
            valid=True,
            skipped_regions=["standalone", "insight"],
            counters={
                "snapshot_item_count": 1,
                "selected_item_count": 1,
                "selected_new_item_count": 1,
                "hotlist_group_count": 1,
                "new_item_count": 1,
                "standalone_section_count": 0,
                "insight_section_count": 0,
                "failed_source_count": 0,
                "skipped_region_count": 2,
            },
        ),
        diagnostics={
            "snapshot_summary": {"total_items": 1},
            "selection": {"strategy": "keyword", "diagnostics": {}},
            "insight": {"enabled": False, "strategy": "noop", "diagnostics": {}},
            "failed_sources": [],
        },
    )


def run_test_notification(config: Dict) -> bool:
    test_config = copy.deepcopy(config)
    display_regions = test_config.setdefault("DISPLAY", {}).setdefault("REGIONS", {})
    display_regions.update(
        {
            "HOTLIST": True,
            "NEW_ITEMS": False,
            "STANDALONE": False,
            "INSIGHT": False,
        }
    )

    test_ctx = AppContext(test_config)
    try:
        if not test_config.get("GENERIC_WEBHOOK_URL"):
            print("未配置 Generic Webhook，无法执行通知测试")
            return False

        proxy_url = test_config.get("DEFAULT_PROXY", "") if test_config.get("USE_PROXY") else None
        if proxy_url:
            print("[代理] 已启用通知测试代理")

        report_package = _build_test_package(test_ctx)

        print("=" * 60)
        print("通知发送测试")
        print("=" * 60)

        render_result = test_ctx.run_render_stage(
            report_package,
            emit_html=True,
            emit_notification=True,
            display_regions=["hotlist"],
        )
        html_file_path = render_result.html.file_path or ""
        if html_file_path:
            print(f"[输出] HTML 报告: {html_file_path}")

        delivery_result = test_ctx.run_delivery_stage(
            render_result.payloads,
            proxy_url=proxy_url,
        )

        if not getattr(delivery_result, "channel_results", None):
            print("通知渠道没有返回任何发送结果")
            return False

        print("-" * 60)
        success_count = 0
        channel_results = delivery_result.channel_results
        for channel_result in channel_results:
            if channel_result.success:
                success_count += 1
                print(f"OK {channel_result.channel}: 成功")
            else:
                print(f"FAIL {channel_result.channel}: 失败")

        print("-" * 60)
        print(f"结果: {success_count}/{len(channel_results)} 个渠道发送成功")
        return success_count > 0
    finally:
        test_ctx.cleanup()
