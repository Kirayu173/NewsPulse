# coding=utf-8
"""Notification sender implementations."""

from __future__ import annotations

import json
from typing import Optional

import requests

from newspulse.utils.logging import get_logger

logger = get_logger(__name__)


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
                logger.error("%s JSON 模板错误: %s", log_prefix, exc)
                payload = {"title": title, "content": content}
        else:
            payload = {"title": title, "content": content}

        headers = {"Content-Type": "application/json"}
        proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
        response = requests.post(
            webhook_url,
            headers=headers,
            json=payload,
            proxies=proxies,
            timeout=30,
        )

        if 200 <= response.status_code < 300:
            logger.info("%s发送成功 [%s]", log_prefix, title)
            return True

        logger.error(
            "%s发送失败 [%s]，状态码：%s, 响应: %s",
            log_prefix,
            title,
            response.status_code,
            response.text,
        )
        return False
    except Exception:
        logger.exception("%s发送异常 [%s]", log_prefix, title)
        return False
