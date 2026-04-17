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


def send_prepared_generic_webhook(
    webhook_url: str,
    payload_template: Optional[str],
    title: str,
    content: str,
    *,
    proxy_url: Optional[str] = None,
    account_label: str = "",
) -> bool:
    """Send a prepared webhook payload without doing any extra rendering."""

    log_prefix = f"通用Webhook{account_label}" if account_label else "通用Webhook"

    try:
        if payload_template:
            json_content = json.dumps(content)[1:-1]
            json_title = json.dumps(title)[1:-1]
            payload_str = payload_template.replace("{content}", json_content).replace("{title}", json_title)
            try:
                payload = json.loads(payload_str)
            except json.JSONDecodeError as exc:
                print(f"{log_prefix} JSON 模板错误: {exc}")
                payload = {"title": title, "content": content}
        else:
            payload = {"title": title, "content": content}

        response = requests.post(
            webhook_url,
            headers=headers,
            json=payload,
            proxies=proxies,
            timeout=30,
        )

        if 200 <= response.status_code < 300:
            print(f"{log_prefix}发送成功 [{title}]")
            return True

        print(f"{log_prefix}发送失败 [{title}]，状态码：{response.status_code}, 响应: {response.text}")
        return False
    except Exception as exc:
        print(f"{log_prefix}发送异常 [{title}]：{exc}")
        return False


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
    """Legacy wrapper that prepares batches before handing off to the sender."""

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

        if not send_prepared_generic_webhook(
            webhook_url=webhook_url,
            payload_template=payload_template,
            title=report_type,
            content=batch_content,
            proxy_url=proxy_url,
            account_label=account_label,
        ):
            return False
        if i < len(batches):
            time.sleep(batch_interval)

    print(f"{log_prefix}共 {len(batches)} 个批次发送完成 [{report_type}]")
    return True
