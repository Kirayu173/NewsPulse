# coding=utf-8
"""Main NewsPulse runner implementation."""

from __future__ import annotations

import os
import webbrowser
from pathlib import Path
from typing import Dict, Optional, Sequence

from newspulse import __version__
from newspulse.core import load_config
from newspulse.core.scheduler import ResolvedSchedule
from newspulse.crawler import CrawlBatchResult, DataFetcher
from newspulse.runtime import (
    assemble_report_package,
    build_runtime,
    run_delivery_stage,
    run_insight_stage,
    run_render_stage,
    run_selection_stage,
)
from newspulse.runner.runtime import (
    ModeStrategy,
    WorkflowExecutionPlan,
    detect_runner_environment,
    resolve_mode_strategy,
)
from newspulse.storage import normalize_crawl_batch
from newspulse.utils.logging import build_log_message, configure_logging, get_logger
from newspulse.utils.time import DEFAULT_TIMEZONE
from newspulse.workflow.shared.contracts import DeliveryPayload, ReportPackage, SelectionResult


logger = get_logger(__name__)


class NewsRunner:
    """Coordinate crawling and native workflow stage orchestration."""

    def __init__(self, config: Optional[Dict] = None):
        configure_logging()
        if config is None:
            logger.info("%s", build_log_message("runner.config_loading"))
            config = load_config()
        configure_logging(
            config.get("LOG_LEVEL", "INFO"),
            config.get("LOG_FILE", ""),
            bool(config.get("LOG_JSON", False)),
        )

        logger.info(
            "%s",
            build_log_message(
                "runner.ready",
                version=__version__,
                platform_count=len(config["PLATFORMS"]),
                timezone=config.get("TIMEZONE", DEFAULT_TIMEZONE),
            ),
        )

        self.runtime = build_runtime(config)
        self.settings = self.runtime.settings
        self.container = self.runtime.container
        self.request_interval = self.settings.crawler.request_interval_ms
        self.report_mode = self.settings.app.default_report_mode
        self.frequency_file: Optional[str] = None
        self.filter_method: Optional[str] = None
        self.interests_file: Optional[str] = None
        self.rank_threshold = self.settings.selection.rank_threshold
        self._initialize_environment()
        self.update_info = None
        self.proxy_url = None

        self._setup_proxy()
        self.data_fetcher = DataFetcher(self.proxy_url)
        self._init_storage_manager()

    def _initialize_environment(self) -> None:
        environment = detect_runner_environment(os.environ)
        self.environment = environment
        self.is_github_actions = environment.is_github_actions
        self.is_docker_container = environment.is_docker_container

    def _init_storage_manager(self) -> None:
        self.storage_manager = self.container.storage()
        logger.info(
            "%s",
            build_log_message("runtime.storage_ready", backend=self.storage_manager.backend_name),
        )

        retention_days = self.settings.storage.retention_days
        if retention_days > 0:
            logger.info(
                "%s",
                build_log_message("runtime.storage_retention", retention_days=retention_days),
            )

    def _should_open_browser(self) -> bool:
        return not self.is_github_actions and not self.is_docker_container

    def _setup_proxy(self) -> None:
        if not self.is_github_actions and self.settings.crawler.proxy_enabled:
            self.proxy_url = self.settings.crawler.default_proxy_url
            logger.info("%s", build_log_message("runtime.proxy_enabled", proxy_url=self.proxy_url))
        elif not self.is_github_actions:
            logger.info("%s", build_log_message("runtime.proxy_disabled"))
        else:
            logger.info("%s", build_log_message("runtime.proxy_skipped", environment="github_actions"))

    def _set_update_info_from_config(self) -> None:
        try:
            version_url = self.settings.app.version_check_url
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
            logger.warning(
                "%s",
                build_log_message("runtime.version_check_failed", error_type=exc.__class__.__name__, error=str(exc)),
            )

    def _get_mode_strategy(self) -> ModeStrategy:
        return resolve_mode_strategy(self.report_mode)

    def _has_notification_configured(self) -> bool:
        return bool(self.settings.delivery.generic_webhook_url)

    def _has_valid_content(self, report_package: ReportPackage) -> bool:
        if not report_package.integrity.valid:
            return False
        selected_count = len(report_package.content.selected_items)
        new_item_count = len(report_package.content.new_items)
        if report_package.meta.mode in {"incremental", "current"}:
            return selected_count > 0
        return selected_count > 0 or new_item_count > 0

    def _log_selection_result(self, selection: SelectionResult) -> None:
        rejected_count = len(getattr(selection, "rejected_items", []) or [])
        logger.info(
            "%s",
            build_log_message(
                "selection.summary",
                strategy=selection.strategy,
                selected=selection.total_selected,
                rejected=rejected_count,
            ),
        )
        if selection.diagnostics.get("fallback_strategy") == "keyword":
            logger.warning(
                "%s",
                build_log_message(
                    "selection.fallback",
                    fallback_strategy="keyword",
                    reason=selection.diagnostics.get("fallback_reason", "unknown error"),
                ),
            )

    def _should_emit_notification(
        self,
        report_package: ReportPackage,
        report_type: str,
        schedule: ResolvedSchedule,
    ) -> bool:
        if not self.settings.delivery.enabled:
            logger.info(
                "%s",
                build_log_message("delivery.skipped", reason="notifications_disabled", report_type=report_type),
            )
            return False

        if not self._has_notification_configured():
            logger.warning("%s", build_log_message("delivery.misconfigured", reason="missing_channel"))
            return False

        if not self._has_valid_content(report_package):
            if not report_package.integrity.valid:
                logger.warning(
                    "%s",
                    build_log_message(
                        "delivery.invalid_report",
                        errors="; ".join(report_package.integrity.errors or ["unknown validation error"]),
                    ),
                )
                return False
            if report_package.meta.mode == "incremental":
                logger.info("%s", build_log_message("delivery.skipped", reason="empty_incremental_report"))
            else:
                logger.info(
                    "%s",
                    build_log_message("delivery.skipped", reason="empty_report", mode=self._get_mode_strategy().mode_name),
                )
            return False

        if not schedule.push:
            logger.info("%s", build_log_message("delivery.skipped", reason="schedule_push_disabled"))
            return False

        if schedule.once_push and schedule.period_key:
            scheduler = self.container.scheduler()
            date_str = self.settings.format_date()
            if scheduler.already_executed(schedule.period_key, "push", date_str):
                logger.info(
                    "%s",
                    build_log_message(
                        "delivery.skipped",
                        reason="period_already_pushed",
                        period=schedule.period_name or schedule.period_key,
                    ),
                )
                return False
            logger.info(
                "%s",
                build_log_message(
                    "delivery.period_ready",
                    period=schedule.period_name or schedule.period_key,
                ),
            )

        return True

    def _run_delivery_if_needed(
        self,
        payloads: Sequence[DeliveryPayload],
        *,
        schedule: ResolvedSchedule,
    ) -> bool:
        if not payloads:
            logger.info("%s", build_log_message("delivery.skipped", reason="no_payloads"))
            return False

        result = run_delivery_stage(
            self.container,
            self.runtime.delivery_builder,
            payloads,
            proxy_url=self.proxy_url,
        )
        if not getattr(result, "channel_results", None):
            logger.warning("%s", build_log_message("delivery.failed", reason="no_channel_results"))
            return False

        if result.success and schedule.once_push and schedule.period_key:
            scheduler = self.container.scheduler()
            scheduler.record_execution(schedule.period_key, "push", self.settings.format_date())

        return result.success

    def _initialize_and_check_config(self) -> None:
        now = self.settings.get_time()
        logger.info(
            "%s",
            build_log_message("runtime.clock_ready", time=now.strftime("%Y-%m-%d %H:%M:%S")),
        )

        if not self.settings.crawler.enabled:
            logger.info("%s", build_log_message("runtime.crawler_disabled"))
            return

        if not self.settings.delivery.enabled:
            logger.info("%s", build_log_message("runtime.notifications_disabled"))
        elif not self._has_notification_configured():
            logger.warning("%s", build_log_message("runtime.notifications_missing"))
        else:
            logger.info("%s", build_log_message("runtime.notifications_ready"))

        mode_strategy = self._get_mode_strategy()
        logger.info(
            "%s",
            build_log_message(
                "runtime.mode_ready",
                report_mode=self.report_mode,
                description=mode_strategy.description,
            ),
        )

    def _crawl_data(self) -> CrawlBatchResult:
        source_specs = self.settings.crawler.crawl_source_specs

        logger.info(
            "%s",
            build_log_message(
                "crawl.start",
                sources=[spec.source_name for spec in source_specs],
                request_interval_ms=self.request_interval,
            ),
        )
        self.settings.storage.data_dir.mkdir(parents=True, exist_ok=True)

        crawl_batch = self.data_fetcher.crawl(source_specs, self.request_interval)

        crawl_time = self.settings.format_time()
        crawl_date = self.settings.format_date()
        normalized_batch = normalize_crawl_batch(crawl_batch, crawl_time, crawl_date)

        if self.storage_manager.save_normalized_crawl_batch(normalized_batch):
            logger.info(
                "%s",
                build_log_message("crawl.persisted", backend=self.storage_manager.backend_name),
            )

        txt_file = self.storage_manager.save_txt_snapshot(normalized_batch)
        if txt_file:
            logger.info("%s", build_log_message("crawl.txt_snapshot_ready", path=txt_file))

        return crawl_batch

    def _resolve_execution_plan(
        self,
        schedule: ResolvedSchedule,
        *,
        mode_strategy: ModeStrategy | None = None,
    ) -> WorkflowExecutionPlan:
        effective_mode = schedule.report_mode
        if effective_mode != self.report_mode:
            logger.info(
                "%s",
                build_log_message("schedule.mode_override", previous=self.report_mode, current=effective_mode),
            )

        active_mode_strategy = mode_strategy if mode_strategy and mode_strategy.mode == effective_mode else resolve_mode_strategy(effective_mode)
        return WorkflowExecutionPlan(
            schedule=schedule,
            report_mode=effective_mode,
            mode_strategy=active_mode_strategy,
            frequency_file=schedule.frequency_file,
            filter_method=schedule.filter_method or self.settings.selection.strategy,
            interests_file=schedule.interests_file,
        )

    def _apply_execution_plan(self, plan: WorkflowExecutionPlan) -> None:
        self.report_mode = plan.report_mode
        self.frequency_file = plan.frequency_file
        self.filter_method = plan.filter_method
        self.interests_file = plan.interests_file

    def _run_workflow_stages(self, plan: WorkflowExecutionPlan) -> ReportPackage:
        snapshot, selection = run_selection_stage(
            self.settings,
            self.container,
            self.runtime.selection_builder,
            mode=plan.report_mode,
            strategy=plan.filter_method,
            frequency_file=plan.frequency_file,
            interests_file=plan.interests_file,
        )
        self._log_selection_result(selection)

        insight = run_insight_stage(
            self.settings,
            self.container,
            self.runtime.selection_builder,
            self.runtime.insight_builder,
            report_mode=plan.report_mode,
            snapshot=snapshot,
            selection=selection,
            strategy=plan.filter_method,
            frequency_file=plan.frequency_file,
            interests_file=plan.interests_file,
            schedule=plan.schedule,
        )
        return assemble_report_package(self.container, snapshot, selection, insight)

    def _render_report(self, plan: WorkflowExecutionPlan, report_package: ReportPackage):
        emit_html = self.settings.storage.enable_html
        emit_notification = plan.mode_strategy.should_send_notification and self._should_emit_notification(
            report_package,
            plan.mode_strategy.report_type,
            plan.schedule,
        )
        render_result = run_render_stage(
            self.container,
            self.runtime.render_builder,
            report_package,
            emit_html=emit_html,
            emit_notification=emit_notification,
            update_info=self.update_info if self.settings.app.show_version_update else None,
        )
        return emit_notification, render_result

    def _handle_html_output(self, html_file: str | None) -> None:
        if not html_file:
            return

        logger.info("%s", build_log_message("render.html_ready", path=html_file))
        latest_file = self.settings.storage.data_dir / "html" / "latest" / f"{self.report_mode}.html"
        logger.info("%s", build_log_message("render.html_latest", path=latest_file))

        if self._should_open_browser():
            file_url = "file://" + str(Path(html_file).resolve())
            logger.info("%s", build_log_message("render.browser_open", url=file_url))
            webbrowser.open(file_url)
        elif self.is_docker_container:
            logger.info("%s", build_log_message("render.browser_skipped", environment="docker", path=html_file))

    def _execute_mode_strategy(
        self,
        mode_strategy: ModeStrategy | None = None,
        schedule: Optional[ResolvedSchedule] = None,
    ) -> Optional[str]:
        resolved_schedule = schedule or self.container.scheduler().resolve()
        plan = self._resolve_execution_plan(resolved_schedule, mode_strategy=mode_strategy)
        self._apply_execution_plan(plan)

        report_package = self._run_workflow_stages(plan)
        emit_notification, render_result = self._render_report(plan, report_package)
        html_file = render_result.html.file_path or None

        if emit_notification:
            self._run_delivery_if_needed(render_result.payloads, schedule=plan.schedule)

        self._handle_html_output(html_file)
        return html_file

    def run(self) -> None:
        try:
            self._initialize_and_check_config()
            if not self.settings.crawler.enabled:
                return

            schedule = self.container.scheduler().resolve()
            if not schedule.collect:
                logger.info("%s", build_log_message("schedule.collect_skipped"))
                return

            mode_strategy = self._get_mode_strategy()
            self._crawl_data()
            self._execute_mode_strategy(mode_strategy, schedule=schedule)
        except Exception:
            logger.exception("%s", build_log_message("runner.failed"))
            if self.settings.app.debug_enabled:
                raise
        finally:
            self.runtime.cleanup()
