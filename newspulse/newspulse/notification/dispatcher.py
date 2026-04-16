# coding=utf-8
"""Notification dispatcher for webhook channels."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

from newspulse.core.config import limit_accounts, parse_multi_account_config

from .senders import send_to_generic_webhook

if TYPE_CHECKING:
    from newspulse.ai import AIAnalysisResult, AITranslator


class NotificationDispatcher:
    """Dispatch translated report content to configured channels."""

    def __init__(
        self,
        config: Dict[str, Any],
        get_time_func: Callable,
        split_content_func: Callable,
        translator: Optional["AITranslator"] = None,
    ):
        self.config = config
        self.get_time_func = get_time_func
        self.split_content_func = split_content_func
        self.max_accounts = config.get("MAX_ACCOUNTS_PER_CHANNEL", 3)
        self.translator = translator

    def translate_content(
        self,
        report_data: Dict,
        standalone_data: Optional[Dict] = None,
        display_regions: Optional[Dict] = None,
    ) -> tuple:
        if not self.translator or not self.translator.enabled:
            return report_data, standalone_data

        import copy

        print(f"[翻译] 正在翻译推送内容到 {self.translator.target_language}...")
        scope = self.translator.scope
        display_regions = display_regions or {}

        report_data = copy.deepcopy(report_data)
        standalone_data = copy.deepcopy(standalone_data) if standalone_data else None

        titles_to_translate = []
        title_locations = []

        if scope.get("HOTLIST", True) and display_regions.get("HOTLIST", True):
            for stat_idx, stat in enumerate(report_data.get("stats", [])):
                for title_idx, title_data in enumerate(stat.get("titles", [])):
                    titles_to_translate.append(title_data.get("title", ""))
                    title_locations.append(("stats", stat_idx, title_idx))

            for source_idx, source in enumerate(report_data.get("new_titles", [])):
                for title_idx, title_data in enumerate(source.get("titles", [])):
                    titles_to_translate.append(title_data.get("title", ""))
                    title_locations.append(("new_titles", source_idx, title_idx))

        if standalone_data and scope.get("STANDALONE", True) and display_regions.get("STANDALONE", False):
            for plat_idx, platform in enumerate(standalone_data.get("platforms", [])):
                for item_idx, item in enumerate(platform.get("items", [])):
                    titles_to_translate.append(item.get("title", ""))
                    title_locations.append(("standalone_platforms", plat_idx, item_idx))

        if not titles_to_translate:
            print("[翻译] 没有可翻译的标题")
            return report_data, standalone_data

        print(f"[翻译] 共 {len(titles_to_translate)} 条标题待翻译")
        result = self.translator.translate_batch(titles_to_translate)

        if result.success_count == 0:
            error = result.results[0].error if result.results else "未知错误"
            print(f"[翻译] 翻译失败: {error}")
            return report_data, standalone_data

        print(f"[翻译] 翻译完成: {result.success_count}/{result.total_count} 条")

        if self.config.get("DEBUG", False):
            if result.prompt:
                print("[翻译][DEBUG] === 完整 AI Prompt ===")
                print(result.prompt)
                print("[翻译][DEBUG] === Prompt 结束 ===")
            if result.raw_response:
                print("[翻译][DEBUG] === AI 原始响应 ===")
                print(result.raw_response)
                print("[翻译][DEBUG] === 原始响应结束 ===")

        for i, (loc_type, idx1, idx2) in enumerate(title_locations):
            if i >= len(result.results) or not result.results[i].success:
                continue
            translated = result.results[i].translated_text
            if loc_type == "stats":
                report_data["stats"][idx1]["titles"][idx2]["title"] = translated
            elif loc_type == "new_titles":
                report_data["new_titles"][idx1]["titles"][idx2]["title"] = translated
            elif loc_type == "standalone_platforms" and standalone_data:
                standalone_data["platforms"][idx1]["items"][idx2]["title"] = translated

        return report_data, standalone_data

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
        del html_file_path
        results: Dict[str, bool] = {}
        display_regions = self.config.get("DISPLAY", {}).get("REGIONS", {})

        if not skip_translation:
            report_data, standalone_data = self.translate_content(
                report_data,
                standalone_data=standalone_data,
                display_regions=display_regions,
            )

        if self.config.get("GENERIC_WEBHOOK_URL"):
            results["generic_webhook"] = self._send_generic_webhook(
                report_data,
                report_type,
                update_info,
                proxy_url,
                mode,
                ai_analysis,
                display_regions,
                standalone_data,
            )

        return results

    def _send_to_multi_accounts(
        self,
        channel_name: str,
        config_value: str,
        send_func: Callable[..., bool],
        **kwargs,
    ) -> bool:
        accounts = parse_multi_account_config(config_value)
        if not accounts:
            return False

        accounts = limit_accounts(accounts, self.max_accounts, channel_name)
        results = []
        for i, account in enumerate(accounts):
            if not account:
                continue
            account_label = f"账号{i + 1}" if len(accounts) > 1 else ""
            results.append(send_func(account, account_label=account_label, **kwargs))

        return any(results) if results else False

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

    def _send_generic_webhook(
        self,
        report_data: Dict,
        report_type: str,
        update_info: Optional[Dict],
        proxy_url: Optional[str],
        mode: str,
        ai_analysis: Optional["AIAnalysisResult"] = None,
        display_regions: Optional[Dict] = None,
        standalone_data: Optional[Dict] = None,
    ) -> bool:
        report_data, ai_analysis, standalone_data = self._apply_display_regions(
            report_data,
            display_regions,
            ai_analysis,
            standalone_data,
        )
        display_regions = display_regions or {}

        urls = parse_multi_account_config(self.config.get("GENERIC_WEBHOOK_URL", ""))
        templates = parse_multi_account_config(self.config.get("GENERIC_WEBHOOK_TEMPLATE", ""))
        if not urls:
            return False

        urls = limit_accounts(urls, self.max_accounts, "通用Webhook")
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
            result = send_to_generic_webhook(
                webhook_url=url,
                payload_template=template,
                report_data=report_data,
                report_type=report_type,
                update_info=update_info,
                proxy_url=proxy_url,
                mode=mode,
                account_label=account_label,
                batch_size=self.config.get("MESSAGE_BATCH_SIZE", 4000),
                batch_interval=self.config.get("BATCH_SEND_INTERVAL", 1.0),
                split_content_func=self.split_content_func,
                ai_analysis=ai_analysis,
                display_regions=display_regions,
                standalone_data=standalone_data,
            )
            results.append(result)

        return any(results) if results else False
