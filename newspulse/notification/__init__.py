# coding=utf-8
"""
通知模块

负责消息拆分、批量发送和通用 Webhook 推送
"""

from newspulse.notification.batch import (
    add_batch_headers,
    get_batch_header,
    get_max_batch_header_size,
    truncate_to_bytes,
)
from newspulse.notification.senders import send_prepared_generic_webhook

__all__ = [
    "get_batch_header",
    "get_max_batch_header_size",
    "truncate_to_bytes",
    "add_batch_headers",
    "send_prepared_generic_webhook",
]
