# coding=utf-8
"""Notification dispatcher for prepared delivery payloads."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional, Sequence

from newspulse.core.config import limit_accounts, parse_multi_account_config
from newspulse.notification.batch import add_batch_headers

from .senders import send_prepared_generic_webhook

if TYPE_CHECKING:
    from newspulse.workflow.shared.contracts import DeliveryPayload


class NotificationDispatcher:
    """Dispatch prepared payloads to configured channels."""

    def __init__(
        self,
        config: Dict[str, Any],
        generic_webhook_sender: Callable[..., bool] = send_prepared_generic_webhook,
    ):
        self.config = config
        self.max_accounts = config.get("MAX_ACCOUNTS_PER_CHANNEL", 3)
        self.generic_webhook_sender = generic_webhook_sender

    def dispatch_payloads(
        self,
        payloads: Sequence["DeliveryPayload"],
        *,
        proxy_url: Optional[str] = None,
        dry_run: bool = False,
    ) -> Dict[str, bool]:
        """Dispatch already-rendered payloads to their target channels."""

        grouped: dict[str, list["DeliveryPayload"]] = defaultdict(list)
        for payload in payloads:
            channel = str(getattr(payload, "channel", "")).strip()
            if channel:
                grouped[channel].append(payload)

        results: Dict[str, bool] = {}
        for channel, channel_payloads in grouped.items():
            if channel == "generic_webhook":
                results[channel] = self._dispatch_generic_webhook_payloads(
                    channel_payloads,
                    proxy_url=proxy_url,
                    dry_run=dry_run,
                )
                continue
            results[channel] = False
        return results

    def _dispatch_generic_webhook_payloads(
        self,
        payloads: Sequence["DeliveryPayload"],
        *,
        proxy_url: Optional[str] = None,
        dry_run: bool = False,
    ) -> bool:
        urls = parse_multi_account_config(self.config.get("GENERIC_WEBHOOK_URL", ""))
        templates = parse_multi_account_config(self.config.get("GENERIC_WEBHOOK_TEMPLATE", ""))
        if not urls or not payloads:
            return False

        urls = limit_accounts(urls, self.max_accounts, "通用Webhook")
        title = str(getattr(payloads[0], "title", "NewsPulse")) if payloads else "NewsPulse"
        if payloads and bool(getattr(payloads[0], "metadata", {}).get("has_batch_headers", False)):
            contents = [str(getattr(payload, "content", "")) for payload in payloads]
        else:
            contents = add_batch_headers(
                [str(getattr(payload, "content", "")) for payload in payloads],
                "generic_webhook",
                self.config.get("MESSAGE_BATCH_SIZE", 4000),
            )
        results = []
        for i, url in enumerate(urls):
            if not url:
                continue

            template = ""
            if templates:
                if i < len(templates):
                    template = templates[i]
                elif len(templates) == 1:
                    template = templates[0]

            account_label = f"账号{i + 1}" if len(urls) > 1 else ""
            if dry_run:
                print(f"通用Webhook{account_label} dry-run：跳过发送 {len(contents)} 个批次 [{title}]")
                results.append(True)
                continue

            account_success = True
            for content in contents:
                if not self.generic_webhook_sender(
                    webhook_url=url,
                    payload_template=template,
                    title=title,
                    content=content,
                    proxy_url=proxy_url,
                    account_label=account_label,
                ):
                    account_success = False
                    break
            results.append(account_success)

        return any(results) if results else False
