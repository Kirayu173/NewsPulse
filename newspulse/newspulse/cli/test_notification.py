# coding=utf-8
"""Notification smoke-test command."""

from __future__ import annotations

import copy
from typing import Dict

from newspulse.context import AppContext
from newspulse.workflow.shared.contracts import (
    HotlistItem,
    InsightResult,
    RenderableReport,
    SelectionGroup,
    SelectionResult,
)


def _build_test_report(ctx: AppContext) -> RenderableReport:
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
    selection = SelectionResult(
        strategy="keyword",
        groups=[SelectionGroup(key="notification_test", label="通知测试", items=[item], position=0)],
        selected_items=[item],
        selected_new_items=[item],
        total_candidates=1,
        total_selected=1,
    )
    return RenderableReport(
        meta={
            "mode": "daily",
            "generated_at": current_time,
            "report_type": "测试通知",
            "timezone": ctx.timezone,
        },
        selection=selection,
        insight=InsightResult(enabled=False, strategy="noop"),
        new_items=[item],
        standalone_sections=[],
        display_regions=["hotlist"],
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

    if "AI_TRANSLATION" in test_config:
        test_config["AI_TRANSLATION"]["ENABLED"] = False

    test_ctx = AppContext(test_config)
    try:
        if not test_config.get("GENERIC_WEBHOOK_URL"):
            print("未配置通用 Webhook，无法执行通知测试")
            return False

        proxy_url = test_config.get("DEFAULT_PROXY", "") if test_config.get("USE_PROXY") else None
        if proxy_url:
            print("[测试] 当前使用代理发送通知")

        report = _build_test_report(test_ctx)
        localized_report = test_ctx.run_localization_stage(report, strategy="noop")

        print("=" * 60)
        print("开始发送测试通知")
        print("=" * 60)

        render_result = test_ctx.run_render_stage(
            localized_report,
            emit_html=True,
            emit_notification=True,
            display_regions=["hotlist"],
        )
        html_file_path = render_result.html.file_path or ""
        if html_file_path:
            print(f"[测试] HTML 已生成: {html_file_path}")

        delivery_result = test_ctx.run_delivery_stage(
            render_result.payloads,
            proxy_url=proxy_url,
        )

        if not getattr(delivery_result, "channel_results", None):
            print("通知发送完成，但没有任何渠道返回结果")
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
        print(f"结果: {success_count}/{len(channel_results)} 个渠道成功")
        return success_count > 0
    finally:
        test_ctx.cleanup()
