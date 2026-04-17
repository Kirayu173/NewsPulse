# coding=utf-8
"""
通知模块

负责消息拆分、批量发送和通用 Webhook 推送
"""

from newspulse.notification.batch import (
    get_batch_header,
    get_max_batch_header_size,
    truncate_to_bytes,
    add_batch_headers,
)
from newspulse.notification.splitter import (
    split_content_into_batches,
    DEFAULT_BATCH_SIZES,
)
from newspulse.notification.senders import send_prepared_generic_webhook, send_to_generic_webhook
from newspulse.notification.dispatcher import NotificationDispatcher

__all__ = [
    "get_batch_header",
    "get_max_batch_header_size",
    "truncate_to_bytes",
    "add_batch_headers",
    "split_content_into_batches",
    "DEFAULT_BATCH_SIZES",
    "send_prepared_generic_webhook",
    "send_to_generic_webhook",
    "NotificationDispatcher",
]
