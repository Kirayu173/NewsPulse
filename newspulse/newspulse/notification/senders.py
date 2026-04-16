# coding=utf-8
"""Notification sender implementations."""

from __future__ import annotations

import json
import time
from typing import Any, Callable, Dict, Optional

import requests

from .batch import add_batch_headers


def _render_ai_analysis(ai_analysis: Any, channel: str) -> str:
    if not ai_analysis:
        return ""

    try:
        from newspulse.ai.formatter import get_ai_analysis_renderer

        renderer = get_ai_analysis_renderer(channel)
        return renderer(ai_analysis)
    except ImportError:
        return ""


def send_to_generic_webhook(
    webhook_url: str,
    payload_template: Optional[str],
    report_data: Dict,
    report_type: str,
    update_info: Optional[Dict] = None,
    proxy_url: Optional[str] = None,
    mode: str = "daily",
    account_label: str = "",
    *,
    batch_size: int = 4000,
    batch_interval: float = 1.0,
    split_content_func: Optional[Callable] = None,
    ai_analysis: Any = None,
    display_regions: Optional[Dict] = None,
    standalone_data: Optional[Dict] = None,
) -> bool:
    del display_regions
    if split_content_func is None:
        raise ValueError("split_content_func is required")

    headers = {"Content-Type": "application/json"}
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
    log_prefix = f"通用Webhook{account_label}" if account_label else "通用Webhook"

    ai_content = None
    ai_stats = None
    if ai_analysis:
        ai_content = _render_ai_analysis(ai_analysis, "wework")
        if getattr(ai_analysis, "success", False):
            ai_stats = {
                "total_news": getattr(ai_analysis, "total_news", 0),
                "analyzed_news": getattr(ai_analysis, "analyzed_news", 0),
                "max_news_limit": getattr(ai_analysis, "max_news_limit", 0),
                "hotlist_count": getattr(ai_analysis, "hotlist_count", 0),
                "ai_mode": getattr(ai_analysis, "ai_mode", ""),
            }

    template_overhead = 200
    batches = split_content_func(
        report_data,
        "wework",
        update_info,
        max_bytes=batch_size - template_overhead,
        mode=mode,
        ai_content=ai_content,
        standalone_data=standalone_data,
        ai_stats=ai_stats,
        report_type=report_type,
    )

    batches = add_batch_headers(batches, "generic_webhook", batch_size)
    print(f"{log_prefix}准备发送 {len(batches)} 个批次 [{report_type}]")

    for i, batch_content in enumerate(batches, 1):
        content_size = len(batch_content.encode("utf-8"))
        print(f"发送{log_prefix}批次 {i}/{len(batches)}，内容大小：{content_size} 字节 [{report_type}]")

        try:
            if payload_template:
                json_content = json.dumps(batch_content)[1:-1]
                json_title = json.dumps(report_type)[1:-1]
                payload_str = payload_template.replace("{content}", json_content).replace("{title}", json_title)
                try:
                    payload = json.loads(payload_str)
                except json.JSONDecodeError as e:
                    print(f"{log_prefix} JSON 模板错误: {e}")
                    payload = {"title": report_type, "content": batch_content}
            else:
                payload = {"title": report_type, "content": batch_content}

            response = requests.post(
                webhook_url,
                headers=headers,
                json=payload,
                proxies=proxies,
                timeout=30,
            )

            if 200 <= response.status_code < 300:
                print(f"{log_prefix}批次 {i}/{len(batches)} 发送成功 [{report_type}]")
                if i < len(batches):
                    time.sleep(batch_interval)
            else:
                print(
                    f"{log_prefix}批次 {i}/{len(batches)} 发送失败 [{report_type}]，"
                    f"状态码：{response.status_code}, 响应: {response.text}"
                )
                return False
        except Exception as e:
            print(f"{log_prefix}批次 {i}/{len(batches)} 发送异常 [{report_type}]：{e}")
            return False

    print(f"{log_prefix}共 {len(batches)} 个批次发送完成 [{report_type}]")
    return True
