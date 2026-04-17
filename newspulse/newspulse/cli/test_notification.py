# coding=utf-8
"""Notification smoke-test command."""

from __future__ import annotations

import copy
from typing import Dict, Optional

from newspulse.context import AppContext


def _build_test_report_data(ctx: AppContext) -> Dict:
    now = ctx.get_time()
    title = f"NewsPulse 测试通知 {now.strftime('%Y-%m-%d %H:%M:%S')}"
    return {
        "stats": [
            {
                "word": "测试关键词",
                "count": 1,
                "titles": [
                    {
                        "title": title,
                        "source_name": "NewsPulse",
                        "url": "",
                        "mobile_url": "",
                        "ranks": [1],
                        "rank_threshold": ctx.rank_threshold,
                        "count": 1,
                        "is_new": True,
                        "time_display": now.strftime('%H:%M'),
                        "matched_keyword": "测试关键词",
                    }
                ],
            }
        ],
        "failed_ids": [],
        "new_titles": [],
        "id_to_name": {},
    }


def _create_test_html_file(ctx: AppContext) -> Optional[str]:
    try:
        now = ctx.get_time()
        output_dir = ctx.get_data_dir() / "html" / ctx.format_date()
        output_dir.mkdir(parents=True, exist_ok=True)
        html_path = output_dir / f"notification_test_{ctx.format_time()}.html"
        html_path.write_text(
            f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>NewsPulse 测试页面</title></head>
<body>
<h2>NewsPulse 通知测试</h2>
<p>生成时间：{now.strftime('%Y-%m-%d %H:%M:%S')} ({ctx.timezone})</p>
<p>这是一份用于通知链路验证的测试 HTML。</p>
</body>
</html>""",
            encoding="utf-8",
        )
        return str(html_path)
    except Exception as exc:
        print(f"[测试] 生成 HTML 失败: {exc}")
        return None


def run_test_notification(config: Dict) -> bool:
    from newspulse.notification import NotificationDispatcher

    test_config = copy.deepcopy(config)
    display_regions = test_config.setdefault("DISPLAY", {}).setdefault("REGIONS", {})
    display_regions.update(
        {
            "HOTLIST": True,
            "NEW_ITEMS": False,
            "STANDALONE": False,
            "AI_ANALYSIS": False,
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

        dispatcher = NotificationDispatcher(
            config=test_config,
            split_content_func=test_ctx.split_content,
        )

        report_data = _build_test_report_data(test_ctx)
        html_file_path = _create_test_html_file(test_ctx)

        print("=" * 60)
        print("开始发送测试通知")
        print("=" * 60)

        results = dispatcher.dispatch_all(
            report_data=report_data,
            report_type="测试通知",
            proxy_url=proxy_url,
            mode="daily",
            html_file_path=html_file_path,
        )

        if not results:
            print("通知发送完成，但没有任何渠道返回结果")
            return False

        print("-" * 60)
        success_count = 0
        for channel, ok in results.items():
            if ok:
                success_count += 1
                print(f"✅ {channel}: 成功")
            else:
                print(f"❌ {channel}: 失败")

        print("-" * 60)
        print(f"结果: {success_count}/{len(results)} 个渠道成功")
        return success_count > 0
    finally:
        test_ctx.cleanup()
