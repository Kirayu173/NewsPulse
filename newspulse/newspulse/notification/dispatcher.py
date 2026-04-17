# coding=utf-8
"""Notification dispatcher for prepared delivery payloads."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional, Sequence

from newspulse.core.config import limit_accounts, parse_multi_account_config
from newspulse.notification.batch import add_batch_headers

from .senders import send_prepared_generic_webhook

if TYPE_CHECKING:
    from newspulse.ai import AIAnalysisResult
    from newspulse.workflow.shared.contracts import DeliveryPayload


class NotificationDispatcher:
    """Dispatch prepared payloads to configured channels."""

    def __init__(
        self,
        config: Dict[str, Any],
        split_content_func: Optional[Callable] = None,
        generic_webhook_sender: Callable[..., bool] = send_prepared_generic_webhook,
    ):
        self.config = config
        self.split_content_func = split_content_func
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

    def dispatch_all(
        self,
        report_data: Dict,
        report_type: str,
        update_info: Optional[Dict] = None,
        proxy_url: Optional[str] = None,
        mode: str = "daily",
        html_file_path: Optional[str] = None,
        ai_analysis: Optional["AIAnalysisResult"] = None,
        standalone_data: Optional[Dict] = None,
        skip_translation: bool = False,
    ) -> Dict[str, bool]:
        """Legacy compatibility wrapper scheduled for removal in later stages."""

        del html_file_path
        del skip_translation
        display_regions = self.config.get("DISPLAY", {}).get("REGIONS", {})
        report_data, ai_analysis, standalone_data = self._apply_display_regions(
            report_data,
            display_regions,
            ai_analysis,
            standalone_data,
        )

        payloads = self._build_legacy_payloads(
            report_data=report_data,
            report_type=report_type,
            update_info=update_info,
            mode=mode,
            ai_analysis=ai_analysis,
            standalone_data=standalone_data,
        )
        return self.dispatch_payloads(payloads, proxy_url=proxy_url)

    def _build_legacy_payloads(
        self,
        *,
        report_data: Dict,
        report_type: str,
        update_info: Optional[Dict],
        mode: str,
        ai_analysis: Optional["AIAnalysisResult"],
        standalone_data: Optional[Dict],
    ) -> list["DeliveryPayload"]:
        if self.split_content_func is None:
            raise ValueError("split_content_func is required for legacy dispatch_all")

        from newspulse.workflow.shared.contracts import DeliveryPayload

        payloads: list[DeliveryPayload] = []
        if self.config.get("GENERIC_WEBHOOK_URL"):
            batches = self._build_generic_webhook_batches(
                report_data=report_data,
                report_type=report_type,
                update_info=update_info,
                mode=mode,
                ai_analysis=ai_analysis,
                standalone_data=standalone_data,
            )
            for index, content in enumerate(batches, start=1):
                payloads.append(
                    DeliveryPayload(
                        channel="generic_webhook",
                        title=report_type,
                        content=content,
                        metadata={
                            "mode": mode,
                            "batch_index": index,
                            "batch_total": len(batches),
                            "legacy_dispatch": True,
                            "has_batch_headers": True,
                        },
                    )
                )
        return payloads

    def _build_generic_webhook_batches(
        self,
        *,
        report_data: Dict,
        report_type: str,
        update_info: Optional[Dict],
        mode: str,
        ai_analysis: Optional["AIAnalysisResult"],
        standalone_data: Optional[Dict],
    ) -> list[str]:
        ai_content = None
        ai_stats = None
        if ai_analysis:
            from newspulse.ai.formatter import get_ai_analysis_renderer

            ai_content = get_ai_analysis_renderer("wework")(ai_analysis)
            if getattr(ai_analysis, "success", False):
                ai_stats = {
                    "total_news": getattr(ai_analysis, "total_news", 0),
                    "analyzed_news": getattr(ai_analysis, "analyzed_news", 0),
                    "max_news_limit": getattr(ai_analysis, "max_news_limit", 0),
                    "hotlist_count": getattr(ai_analysis, "hotlist_count", 0),
                    "ai_mode": getattr(ai_analysis, "ai_mode", ""),
                }

        template_overhead = 200
        batches = self.split_content_func(
            report_data,
            "wework",
            update_info,
            max_bytes=self.config.get("MESSAGE_BATCH_SIZE", 4000) - template_overhead,
            mode=mode,
            ai_content=ai_content,
            standalone_data=standalone_data,
            ai_stats=ai_stats,
            report_type=report_type,
        )
        return add_batch_headers(batches, "generic_webhook", self.config.get("MESSAGE_BATCH_SIZE", 4000))

    def _apply_display_regions(
        self,
        report_data: Dict,
        display_regions: Optional[Dict],
        ai_analysis: Optional["AIAnalysisResult"] = None,
        standalone_data: Optional[Dict] = None,
    ) -> tuple:
        display_regions = display_regions or {}
        if not display_regions.get("HOTLIST", True):
            report_data = {"stats": [], "failed_ids": [], "new_titles": [], "id_to_name": {}, "total_new_count": 0}
        return (
            report_data,
            ai_analysis if display_regions.get("AI_ANALYSIS", True) else None,
            standalone_data if display_regions.get("STANDALONE", False) else None,
        )

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
