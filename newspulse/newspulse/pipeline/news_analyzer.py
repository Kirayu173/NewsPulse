# coding=utf-8
"""Main NewsPulse pipeline implementation."""

from __future__ import annotations

import os
import webbrowser
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from newspulse import __version__
from newspulse.context import AppContext
from newspulse.core import load_config
from newspulse.core.scheduler import ResolvedSchedule
from newspulse.crawler import DataFetcher
from newspulse.storage import convert_crawl_results_to_news_data
from newspulse.utils.time import DEFAULT_TIMEZONE
from newspulse.workflow.shared.contracts import DeliveryPayload, HotlistSnapshot, SelectionResult


class NewsAnalyzer:
    """Coordinate crawling and native workflow stage orchestration."""

    MODE_STRATEGIES = {
        "incremental": {
            "mode_name": "增量",
            "description": "仅分析本次抓取新增的热榜变化",
            "report_type": "增量报告",
            "should_send_notification": True,
        },
        "current": {
            "mode_name": "实时",
            "description": "基于今日已抓取数据生成当前快照",
            "report_type": "实时报告",
            "should_send_notification": True,
        },
        "daily": {
            "mode_name": "日报",
            "description": "汇总今日全部抓取数据生成日报",
            "report_type": "每日报告",
            "should_send_notification": True,
        },
    }

    def __init__(self, config: Optional[Dict] = None):
        if config is None:
            print("正在加载配置...")
            config = load_config()

        print(f"NewsPulse v{__version__} 启动中")
        print(f"已启用平台: {len(config['PLATFORMS'])}")
        print(f"时区: {config.get('TIMEZONE', DEFAULT_TIMEZONE)}")

        self.ctx = AppContext(config)
        self.request_interval = self.ctx.config["REQUEST_INTERVAL"]
        self.report_mode = self.ctx.config["REPORT_MODE"]
        self.frequency_file: Optional[str] = None
        self.filter_method: Optional[str] = None
        self.interests_file: Optional[str] = None
        self.rank_threshold = self.ctx.rank_threshold
        self.is_github_actions = os.environ.get("GITHUB_ACTIONS") == "true"
        self.is_docker_container = self._detect_docker_environment()
        self.update_info = None
        self.proxy_url = None

        self._setup_proxy()
        self.data_fetcher = DataFetcher(self.proxy_url)
        self._init_storage_manager()

    def _init_storage_manager(self) -> None:
        env_retention = os.environ.get("STORAGE_RETENTION_DAYS", "").strip()
        if env_retention:
            self.ctx.config.setdefault("STORAGE", {}).setdefault("LOCAL", {})["RETENTION_DAYS"] = int(env_retention)

        self.storage_manager = self.ctx.get_storage_manager()
        print(f"存储: {self.storage_manager.backend_name}")

        retention_days = self.ctx.config.get("STORAGE", {}).get("LOCAL", {}).get("RETENTION_DAYS", 0)
        if retention_days > 0:
            print(f"数据保留: {retention_days} 天")

    def _detect_docker_environment(self) -> bool:
        try:
            if os.environ.get("DOCKER_CONTAINER") == "true":
                return True
            return os.path.exists("/.dockerenv")
        except Exception:
            return False

    def _should_open_browser(self) -> bool:
        return not self.is_github_actions and not self.is_docker_container

    def _setup_proxy(self) -> None:
        if not self.is_github_actions and self.ctx.config["USE_PROXY"]:
            self.proxy_url = self.ctx.config["DEFAULT_PROXY"]
            print("已启用代理")
        elif not self.is_github_actions:
            print("未启用代理")
        else:
            print("GitHub Actions 环境，跳过代理设置")

    def _set_update_info_from_config(self) -> None:
        try:
            version_url = self.ctx.config.get("VERSION_CHECK_URL", "")
            if not version_url:
                return
            from newspulse.cli.versioning import _fetch_remote_version, _parse_version

            remote_version = _fetch_remote_version(version_url, self.proxy_url)
            if remote_version and _parse_version(__version__) < _parse_version(remote_version):
                self.update_info = {
                    "current_version": __version__,
                    "remote_version": remote_version,
                }
        except Exception as exc:
            print(f"版本检查失败: {exc}")

    def _get_mode_strategy(self) -> Dict:
        return self.MODE_STRATEGIES.get(self.report_mode, self.MODE_STRATEGIES["daily"])

    def _has_notification_configured(self) -> bool:
        return bool(self.ctx.config.get("GENERIC_WEBHOOK_URL"))

    def _has_valid_content(self, snapshot: HotlistSnapshot, selection: SelectionResult) -> bool:
        if snapshot.mode in {"incremental", "current"}:
            return selection.total_selected > 0
        return selection.total_selected > 0 or bool(snapshot.new_items)

    def _log_selection_result(self, selection: SelectionResult) -> None:
        if selection.strategy == "ai":
            print(
                f"[筛选] 使用 AI selection stage: {selection.total_selected} 条新闻, "
                f"{len(selection.groups)} 个标签组"
            )
        else:
            print(
                f"[筛选] 使用 keyword selection stage: {selection.total_selected} 条新闻, "
                f"{len(selection.groups)} 个分组"
            )
        if selection.diagnostics.get("fallback_strategy") == "keyword":
            print(
                f"[筛选] AI selection 失败，已回退到 keyword: "
                f"{selection.diagnostics.get('fallback_reason', 'unknown error')}"
            )

    def _should_emit_notification(
        self,
        snapshot: HotlistSnapshot,
        selection: SelectionResult,
        report_type: str,
        schedule: ResolvedSchedule,
    ) -> bool:
        cfg = self.ctx.config
        if not cfg["ENABLE_NOTIFICATION"]:
            print(f"已关闭 {report_type} 通知发送")
            return False

        if not self._has_notification_configured():
            print("已启用通知，但未配置任何可用通知渠道")
            return False

        if not self._has_valid_content(snapshot, selection):
            if snapshot.mode == "incremental":
                print("增量模式下没有新增内容，跳过通知")
            else:
                print(f"当前{self._get_mode_strategy()['mode_name']}没有可发送内容")
            return False

        if not schedule.push:
            print("[推送] 当前时段未配置消息推送")
            return False

        if schedule.once_push and schedule.period_key:
            scheduler = self.ctx.create_scheduler()
            date_str = self.ctx.format_date()
            if scheduler.already_executed(schedule.period_key, "push", date_str):
                print(f"[推送] 推送计划 {schedule.period_name or schedule.period_key} 今日已执行")
                return False
            print(f"[推送] 推送计划 {schedule.period_name or schedule.period_key} 准备执行")

        return True

    def _run_delivery_if_needed(
        self,
        payloads: Sequence[DeliveryPayload],
        *,
        schedule: ResolvedSchedule,
    ) -> bool:
        if not payloads:
            print("[推送] render stage 未生成任何可发送 payload")
            return False

        result = self.ctx.run_delivery_stage(payloads, proxy_url=self.proxy_url)
        if not getattr(result, "channel_results", None):
            print("通知渠道没有返回任何结果")
            return False

        if result.success and schedule.once_push and schedule.period_key:
            scheduler = self.ctx.create_scheduler()
            scheduler.record_execution(schedule.period_key, "push", self.ctx.format_date())

        return result.success

    def _initialize_and_check_config(self) -> None:
        now = self.ctx.get_time()
        print(f"当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")

        if not self.ctx.config["ENABLE_CRAWLER"]:
            print("爬虫已禁用（ENABLE_CRAWLER=False），程序结束")
            return

        if not self.ctx.config["ENABLE_NOTIFICATION"]:
            print("通知已禁用（ENABLE_NOTIFICATION=False），仅生成本地结果")
        elif not self._has_notification_configured():
            print("通知功能已开启，但未检测到可用渠道")
        else:
            print("通知渠道检查通过")

        mode_strategy = self._get_mode_strategy()
        print(f"模式: {self.report_mode}")
        print(f"说明: {mode_strategy['description']}")

    def _crawl_data(self) -> Tuple[Dict, Dict, List]:
        ids = []
        for platform in self.ctx.platforms:
            if "name" in platform:
                ids.append((platform["id"], platform["name"]))
            else:
                ids.append(platform["id"])

        print(f"本次抓取平台: {[p.get('name', p['id']) for p in self.ctx.platforms]}")
        print(f"请求间隔: 每个平台等待 {self.request_interval} 秒")
        self.ctx.get_data_dir().mkdir(parents=True, exist_ok=True)

        results, id_to_name, failed_ids = self.data_fetcher.crawl_websites(ids, self.request_interval)

        crawl_time = self.ctx.format_time()
        crawl_date = self.ctx.format_date()
        news_data = convert_crawl_results_to_news_data(results, id_to_name, failed_ids, crawl_time, crawl_date)

        if self.storage_manager.save_news_data(news_data):
            print(f"抓取结果已写入存储: {self.storage_manager.backend_name}")

        txt_file = self.storage_manager.save_txt_snapshot(news_data)
        if txt_file:
            print(f"TXT 快照已保存: {txt_file}")

        return results, id_to_name, failed_ids

    def _execute_mode_strategy(
        self,
        mode_strategy: Dict,
        results: Dict,
        id_to_name: Dict,
        failed_ids: List,
        schedule: Optional[ResolvedSchedule] = None,
    ) -> Optional[str]:
        del results
        del id_to_name
        del failed_ids

        schedule = schedule or self.ctx.create_scheduler().resolve()

        effective_mode = schedule.report_mode
        if effective_mode != self.report_mode:
            print(f"[计划] 模式调整: {self.report_mode} -> {effective_mode}")
        self.report_mode = effective_mode
        mode_strategy = self._get_mode_strategy()

        self.frequency_file = schedule.frequency_file
        self.filter_method = schedule.filter_method or self.ctx.filter_method
        self.interests_file = schedule.interests_file

        snapshot, selection = self.ctx.run_selection_stage(
            mode=self.report_mode,
            strategy=self.filter_method,
            frequency_file=self.frequency_file,
            interests_file=self.interests_file,
        )
        self._log_selection_result(selection)

        insight, _ = self.ctx.run_insight_stage(
            report_mode=self.report_mode,
            snapshot=snapshot,
            selection=selection,
            strategy=self.filter_method,
            frequency_file=self.frequency_file,
            interests_file=self.interests_file,
            schedule=schedule,
        )
        report = self.ctx.assemble_renderable_report(snapshot, selection, insight)
        localized_report = self.ctx.run_localization_stage(report)

        emit_html = bool(self.ctx.config["STORAGE"]["FORMATS"].get("HTML", True))
        emit_notification = mode_strategy["should_send_notification"] and self._should_emit_notification(
            snapshot,
            selection,
            mode_strategy["report_type"],
            schedule,
        )
        render_result = self.ctx.run_render_stage(
            localized_report,
            emit_html=emit_html,
            emit_notification=emit_notification,
            update_info=self.update_info if self.ctx.config.get("SHOW_VERSION_UPDATE", False) else None,
        )
        html_file = render_result.html.file_path or None

        if html_file:
            print(f"HTML 报告已生成: {html_file}")
            latest_file = self.ctx.get_data_dir() / "html" / "latest" / f"{self.report_mode}.html"
            print(f"最新快照链接: {latest_file}")

        if emit_notification:
            self._run_delivery_if_needed(render_result.payloads, schedule=schedule)

        if self._should_open_browser() and html_file:
            file_url = "file://" + str(Path(html_file).resolve())
            print(f"正在打开 HTML 报告: {file_url}")
            webbrowser.open(file_url)
        elif self.is_docker_container and html_file:
            print(f"HTML 报告已生成，请在容器内手动查看: {html_file}")

        return html_file

    def run(self) -> None:
        try:
            self._initialize_and_check_config()
            if not self.ctx.config["ENABLE_CRAWLER"]:
                return

            schedule = self.ctx.create_scheduler().resolve()
            if not schedule.collect:
                print("[计划] 当前时段不执行抓取任务")
                return

            mode_strategy = self._get_mode_strategy()
            results, id_to_name, failed_ids = self._crawl_data()
            self._execute_mode_strategy(mode_strategy, results, id_to_name, failed_ids, schedule=schedule)
        except Exception as exc:
            print(f"运行异常: {exc}")
            if self.ctx.config.get("DEBUG", False):
                raise
        finally:
            self.ctx.cleanup()
