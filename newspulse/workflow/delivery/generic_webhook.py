# coding=utf-8
"""Generic webhook adapter for the workflow delivery stage."""

from __future__ import annotations

from typing import Any, Callable, Sequence

from newspulse.core.config import limit_accounts, parse_multi_account_config
from newspulse.notification.batch import add_batch_headers
from newspulse.notification.senders import send_prepared_generic_webhook
from newspulse.utils.logging import get_logger
from newspulse.workflow.delivery.models import ChannelDeliveryResult
from newspulse.workflow.shared.contracts import DeliveryPayload

logger = get_logger(__name__)


class GenericWebhookDeliveryAdapter:
    """Deliver prepared payloads to configured generic webhook endpoints."""

    def __init__(
        self,
        config: dict[str, Any],
        *,
        sender_func: Callable[..., bool] = send_prepared_generic_webhook,
    ):
        self.config = config
        self.sender_func = sender_func
        self.max_accounts = int(config.get("MAX_ACCOUNTS_PER_CHANNEL", 3) or 3)
        self.batch_size = int(config.get("MESSAGE_BATCH_SIZE", 4000) or 4000)

    def run(
        self,
        payloads: Sequence[DeliveryPayload],
        *,
        proxy_url: str | None = None,
        dry_run: bool = False,
    ) -> ChannelDeliveryResult:
        """Deliver a batch of prepared generic-webhook payloads."""

        payload_list = [payload for payload in payloads if payload.channel == "generic_webhook"]
        if not payload_list:
            return ChannelDeliveryResult(channel="generic_webhook", skipped=True)

        urls = parse_multi_account_config(self.config.get("GENERIC_WEBHOOK_URL", ""))
        templates = parse_multi_account_config(self.config.get("GENERIC_WEBHOOK_TEMPLATE", ""))
        if not urls:
            return ChannelDeliveryResult(
                channel="generic_webhook",
                attempted_payloads=len(payload_list),
                skipped=True,
                metadata={"reason": "missing webhook url"},
            )

        urls = limit_accounts(urls, self.max_accounts, "通用Webhook")
        title = payload_list[0].title
        contents = add_batch_headers(
            [payload.content for payload in payload_list],
            "generic_webhook",
            self.batch_size,
        )

        account_results: list[bool] = []
        for index, url in enumerate(urls):
            if not url:
                continue

            template = ""
            if templates:
                if index < len(templates):
                    template = templates[index]
                elif len(templates) == 1:
                    template = templates[0]

            account_label = f"账号{index + 1}" if len(urls) > 1 else ""
            if dry_run:
                logger.info(
                    "通用Webhook%s dry-run：跳过发送 %s 个批次 [%s]",
                    account_label,
                    len(contents),
                    title,
                )
                account_results.append(True)
                continue

            account_success = True
            for content in contents:
                if not self.sender_func(
                    webhook_url=url,
                    payload_template=template,
                    title=title,
                    content=content,
                    proxy_url=proxy_url,
                    account_label=account_label,
                ):
                    account_success = False
                    break
            account_results.append(account_success)

        success = any(account_results) if account_results else False
        delivered_payloads = len(payload_list) if success else 0
        return ChannelDeliveryResult(
            channel="generic_webhook",
            attempted_payloads=len(payload_list),
            delivered_payloads=delivered_payloads,
            success=success,
            metadata={
                "account_count": len([url for url in urls if url]),
                "rendered_batch_count": len(contents),
                "dry_run": dry_run,
            },
        )
