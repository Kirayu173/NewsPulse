# coding=utf-8
"""Application context helpers."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from newspulse.core import Scheduler
from newspulse.core.runtime_config import (
    DEFAULT_REGION_ORDER,
    REGION_FLAG_DEFAULTS,
    REGION_FLAG_KEYS,
    normalize_runtime_config,
)
from newspulse.core.scheduler import ResolvedSchedule
from newspulse.crawler import CrawlSourceSpec
from newspulse.crawler.source_names import resolve_source_display_name
from newspulse.storage import get_storage_manager
from newspulse.utils.time import (
    DEFAULT_TIMEZONE,
    format_date_folder,
    format_time_filename,
    get_configured_time,
    get_current_time_display,
)
from newspulse.workflow.delivery import DeliveryService, GenericWebhookDeliveryAdapter
from newspulse.workflow.insight import InsightService
from newspulse.workflow.report import ReportPackageAssembler
from newspulse.workflow.selection import SelectionService
from newspulse.workflow.selection.ai import build_embedding_runtime_config
from newspulse.workflow.shared.contracts import (
    HotlistSnapshot,
    InsightResult,
    ReportPackage,
    SelectionResult,
)
from newspulse.workflow.shared.options import (
    DeliveryOptions,
    InsightOptions,
    RenderOptions,
    SelectionAIOptions,
    SelectionOptions,
    SelectionSemanticOptions,
    SnapshotOptions,
)
from newspulse.workflow.snapshot import SnapshotService

if TYPE_CHECKING:
    from newspulse.storage.manager import StorageManager
    from newspulse.workflow.render.service import RenderService


class AppConfigView:
    """Read-only view over normalized runtime configuration."""

    def __init__(self, config: Dict[str, Any]):
        raw_config = deepcopy(config) if isinstance(config, dict) else {}
        self._raw_config = raw_config
        self.config = normalize_runtime_config(raw_config, raw_config=raw_config)

    @property
    def workflow_config(self) -> Dict[str, Any]:
        workflow = self.config.get("WORKFLOW", {})
        return workflow if isinstance(workflow, dict) else {}

    @property
    def raw_ai_config(self) -> Dict[str, Any]:
        ai = self._raw_config.get("ai", {})
        return ai if isinstance(ai, dict) else {}

    @property
    def timezone(self) -> str:
        return self.config.get("TIMEZONE", DEFAULT_TIMEZONE)

    @property
    def rank_threshold(self) -> int:
        return int(self.config.get("RANK_THRESHOLD", 50) or 50)

    @property
    def weight_config(self) -> Dict[str, Any]:
        weight = self.config.get("WEIGHT_CONFIG", {})
        return dict(weight) if isinstance(weight, dict) else {}

    @property
    def platforms(self) -> List[Dict[str, Any]]:
        platforms = self.config.get("PLATFORMS", [])
        return [dict(platform) for platform in platforms if isinstance(platform, dict)]

    @property
    def platform_ids(self) -> List[str]:
        return [platform.get("id", "") for platform in self.platforms if platform.get("id")]

    @property
    def platform_name_map(self) -> Dict[str, str]:
        return {
            platform.get("id", ""): resolve_source_display_name(
                platform.get("id", ""),
                str(platform.get("name", "") or ""),
            )
            for platform in self.platforms
            if platform.get("id")
        }

    @property
    def crawl_source_specs(self) -> List[CrawlSourceSpec]:
        return [
            CrawlSourceSpec(source_id=source_id, source_name=source_name)
            for source_id, source_name in self.platform_name_map.items()
        ]

    @property
    def display_mode(self) -> str:
        return str(self.config.get("DISPLAY_MODE", "keyword") or "keyword")

    @property
    def display_config(self) -> Dict[str, Any]:
        display = self.config.get("DISPLAY", {})
        return dict(display) if isinstance(display, dict) else {}

    @property
    def show_new_section(self) -> bool:
        return bool(self.display_config.get("REGIONS", {}).get("NEW_ITEMS", True))

    @property
    def region_order(self) -> List[str]:
        display = self.display_config
        configured_order = display.get("REGION_ORDER")
        base_order = configured_order if isinstance(configured_order, list) and configured_order else DEFAULT_REGION_ORDER
        regions = display.get("REGIONS")

        if not isinstance(regions, dict) or not regions:
            normalized_defaults: List[str] = []
            for region in base_order:
                region_name = str(region or "").strip().lower()
                if region_name in REGION_FLAG_KEYS and region_name not in normalized_defaults:
                    normalized_defaults.append(region_name)
            return normalized_defaults or list(DEFAULT_REGION_ORDER)

        normalized: List[str] = []
        for region in base_order:
            region_name = str(region or "").strip().lower()
            if region_name not in REGION_FLAG_KEYS or region_name in normalized:
                continue
            enabled = regions.get(REGION_FLAG_KEYS[region_name], REGION_FLAG_DEFAULTS[region_name])
            if enabled:
                normalized.append(region_name)

        if normalized or isinstance(configured_order, list):
            return normalized
        return list(DEFAULT_REGION_ORDER)

    @property
    def selection_stage_config(self) -> Dict[str, Any]:
        selection = self.workflow_config.get("SELECTION", {})
        return dict(selection) if isinstance(selection, dict) else {}

    @property
    def insight_stage_config(self) -> Dict[str, Any]:
        insight = self.workflow_config.get("INSIGHT", {})
        return dict(insight) if isinstance(insight, dict) else {}

    @property
    def filter_method(self) -> str:
        return str(self.selection_stage_config.get("STRATEGY", "keyword") or "keyword")

    @property
    def ai_priority_sort_enabled(self) -> bool:
        return bool(self.selection_stage_config.get("PRIORITY_SORT_ENABLED", False))

    @property
    def request_interval_ms(self) -> int:
        return int(self.config.get("REQUEST_INTERVAL", 100) or 100)

    @property
    def default_report_mode(self) -> str:
        return str(self.config.get("REPORT_MODE", "daily") or "daily")

    @property
    def crawler_enabled(self) -> bool:
        return bool(self.config.get("ENABLE_CRAWLER", True))

    @property
    def notification_enabled(self) -> bool:
        return bool(self.config.get("ENABLE_NOTIFICATION", True))

    @property
    def generic_webhook_url(self) -> str:
        return str(self.config.get("GENERIC_WEBHOOK_URL", "") or "")

    @property
    def proxy_enabled(self) -> bool:
        return bool(self.config.get("USE_PROXY", False))

    @property
    def default_proxy_url(self) -> str:
        return str(self.config.get("DEFAULT_PROXY", "") or "")

    @property
    def show_version_update(self) -> bool:
        return bool(self.config.get("SHOW_VERSION_UPDATE", False))

    @property
    def debug_enabled(self) -> bool:
        return bool(self.config.get("DEBUG", False))

    @property
    def max_news_per_keyword(self) -> int:
        return int(self.config.get("MAX_NEWS_PER_KEYWORD", 0) or 0)

    @property
    def sort_by_position_first(self) -> bool:
        return bool(self.config.get("SORT_BY_POSITION_FIRST", False))

    @property
    def message_batch_size(self) -> int:
        return int(self.config.get("MESSAGE_BATCH_SIZE", 4000) or 4000)

    @property
    def storage_config(self) -> Dict[str, Any]:
        storage = self.config.get("STORAGE", {})
        return dict(storage) if isinstance(storage, dict) else {}

    @property
    def storage_formats(self) -> Dict[str, Any]:
        formats = self.storage_config.get("FORMATS", {})
        return dict(formats) if isinstance(formats, dict) else {}

    @property
    def storage_local_config(self) -> Dict[str, Any]:
        local = self.storage_config.get("LOCAL", {})
        return dict(local) if isinstance(local, dict) else {}

    @property
    def storage_backend_type(self) -> str:
        return str(self.storage_config.get("BACKEND", "local") or "local")

    @property
    def storage_retention_days(self) -> int:
        return int(self.storage_local_config.get("RETENTION_DAYS", 0) or 0)

    @property
    def ai_filter_config(self) -> Dict[str, Any]:
        config = self.config.get("AI_FILTER", {})
        return dict(config) if isinstance(config, dict) else {}

    @property
    def ai_analysis_config(self) -> Dict[str, Any]:
        config = self.config.get("AI_ANALYSIS", {})
        return dict(config) if isinstance(config, dict) else {}

    @property
    def ai_analysis_model_config(self) -> Dict[str, Any]:
        config = self.config.get("AI_ANALYSIS_MODEL", {})
        return dict(config) if isinstance(config, dict) else {}

    @property
    def ai_filter_model_config(self) -> Dict[str, Any]:
        config = self.config.get("AI_FILTER_MODEL", {})
        return dict(config) if isinstance(config, dict) else {}

    @property
    def ai_filter_embedding_model_config(self) -> Dict[str, Any]:
        return build_embedding_runtime_config(self.ai_filter_model_config)

    @property
    def ai_runtime_config(self) -> Dict[str, Any]:
        config = self.config.get("AI", {})
        return dict(config) if isinstance(config, dict) else {}

    @property
    def config_root(self) -> Path:
        config_root = self.config.get("_PATHS", {}).get("CONFIG_ROOT")
        return Path(config_root) if config_root else Path("config")

    def get_time(self) -> datetime:
        return get_configured_time(self.timezone)

    def format_date(self) -> str:
        return format_date_folder(timezone=self.timezone)

    def format_time(self) -> str:
        return format_time_filename(self.timezone)

    def get_time_display(self) -> str:
        return get_current_time_display(self.timezone)

    def get_data_dir(self) -> Path:
        return Path(self.storage_local_config.get("DATA_DIR", "output"))

    def get_output_path(self, subfolder: str, filename: str) -> str:
        output_dir = self.get_data_dir() / subfolder / self.format_date()
        output_dir.mkdir(parents=True, exist_ok=True)
        return str(output_dir / filename)

    def build_selection_options(
        self,
        *,
        strategy: Optional[str] = None,
        frequency_file: Optional[str] = None,
        interests_file: Optional[str] = None,
    ) -> SelectionOptions:
        selection_config = self.selection_stage_config
        selection_ai = selection_config.get("AI", {})
        selection_semantic = selection_config.get("SEMANTIC", {})
        effective_interests_file = interests_file or selection_ai.get("INTERESTS_FILE") or "ai_interests.txt"
        return SelectionOptions(
            strategy=strategy or str(selection_config.get("STRATEGY", "keyword") or "keyword"),
            frequency_file=frequency_file or selection_config.get("FREQUENCY_FILE"),
            priority_sort_enabled=self.ai_priority_sort_enabled,
            ai=SelectionAIOptions(
                interests_file=effective_interests_file,
                batch_size=int(selection_ai.get("BATCH_SIZE", 200) or 200),
                batch_interval=float(selection_ai.get("BATCH_INTERVAL", 5) or 0),
                min_score=float(selection_ai.get("MIN_SCORE", 0) or 0),
                fallback_to_keyword=bool(selection_ai.get("FALLBACK_TO_KEYWORD", True)),
            ),
            semantic=SelectionSemanticOptions(
                enabled=bool(selection_semantic.get("ENABLED", True)),
                top_k=int(selection_semantic.get("TOP_K", 3) or 3),
                min_score=float(selection_semantic.get("MIN_SCORE", 0.55) or 0.55),
                direct_threshold=float(selection_semantic.get("DIRECT_THRESHOLD", 0.78) or 0.78),
            ),
        )

    def build_insight_options(self, *, report_mode: str) -> InsightOptions:
        analysis_config = self.insight_stage_config
        enabled = bool(analysis_config.get("ENABLED", False))
        configured_strategy = str(
            analysis_config.get("STRATEGY", "ai" if enabled else "noop")
            or ("ai" if enabled else "noop")
        ).strip()
        requested_mode = str(analysis_config.get("MODE", "follow_report") or "follow_report").strip()
        effective_mode = report_mode

        return InsightOptions(
            enabled=enabled,
            strategy=configured_strategy or ("ai" if enabled else "noop"),
            mode=effective_mode,
            max_items=int(analysis_config.get("MAX_ITEMS", 50) or 50),
            metadata={
                "requested_mode": requested_mode,
                "report_mode": report_mode,
                "mode_resolved_by_context": requested_mode != report_mode,
            },
        )

    def build_render_options(
        self,
        *,
        emit_html: Optional[bool] = None,
        emit_notification: Optional[bool] = None,
        display_regions: Optional[List[str]] = None,
        update_info: Optional[Dict[str, Any]] = None,
    ) -> RenderOptions:
        notification_channels = self._get_render_notification_channels()
        metadata: Dict[str, Any] = {}
        if update_info:
            metadata["update_info"] = dict(update_info)

        return RenderOptions(
            display_regions=list(display_regions or self.region_order),
            emit_html=True if emit_html is None else emit_html,
            emit_notification=bool(notification_channels) if emit_notification is None else emit_notification,
            metadata=metadata,
        )

    def build_delivery_options(
        self,
        *,
        enabled: Optional[bool] = None,
        channels: Optional[List[str]] = None,
        dry_run: bool = False,
        proxy_url: Optional[str] = None,
    ) -> DeliveryOptions:
        effective_channels = list(channels or self._get_render_notification_channels())
        metadata: Dict[str, Any] = {}
        if proxy_url:
            metadata["proxy_url"] = proxy_url

        return DeliveryOptions(
            enabled=self.notification_enabled if enabled is None else enabled,
            channels=effective_channels,
            dry_run=dry_run,
            metadata=metadata,
        )

    def _get_render_notification_channels(self) -> List[str]:
        channels: List[str] = []
        if self.generic_webhook_url:
            channels.append("generic_webhook")
        return channels


class ServiceFactory:
    """Centralize workflow service construction for the runtime facade."""

    def __init__(self, runtime: "WorkflowRuntimeFacade"):
        self.runtime = runtime

    def create_snapshot_service(self) -> SnapshotService:
        cfg = self.runtime.config_view
        standalone_config = cfg.display_config.get("STANDALONE", {})
        return SnapshotService(
            self.runtime.get_storage_manager(),
            platform_ids=cfg.platform_ids,
            platform_names=cfg.platform_name_map,
            standalone_platform_ids=standalone_config.get("PLATFORMS", []),
            standalone_max_items=standalone_config.get("MAX_ITEMS", 20),
        )

    def create_selection_service(self) -> SelectionService:
        cfg = self.runtime.config_view
        return SelectionService(
            config_root=str(cfg.config_root),
            rank_threshold=cfg.rank_threshold,
            weight_config=cfg.weight_config,
            max_news_per_keyword=cfg.max_news_per_keyword,
            sort_by_position_first=cfg.sort_by_position_first,
            storage_manager=self.runtime.get_storage_manager(),
            ai_runtime_config=cfg.ai_filter_model_config,
            embedding_runtime_config=cfg.ai_filter_embedding_model_config,
            ai_filter_config=cfg.ai_filter_config,
            debug=cfg.debug_enabled,
        )

    def create_insight_service(self) -> InsightService:
        cfg = self.runtime.config_view
        return InsightService(
            ai_runtime_config=cfg.ai_analysis_model_config,
            ai_analysis_config=cfg.ai_analysis_config,
            config_root=str(cfg.config_root),
            storage_manager=self.runtime.get_storage_manager(),
            proxy_url=cfg.default_proxy_url if cfg.proxy_enabled else None,
        )

    def create_report_assembler(self) -> ReportPackageAssembler:
        cfg = self.runtime.config_view
        return ReportPackageAssembler(
            timezone=cfg.timezone,
            display_mode=cfg.display_mode,
        )

    def create_render_service(self) -> "RenderService":
        from newspulse.workflow.render.html import HTMLRenderAdapter
        from newspulse.workflow.render.notification import NotificationRenderAdapter
        from newspulse.workflow.render.service import RenderService

        cfg = self.runtime.config_view
        html_adapter = HTMLRenderAdapter(
            output_dir=str(cfg.get_data_dir()),
            get_time_func=cfg.get_time,
            date_folder_func=cfg.format_date,
            time_filename_func=cfg.format_time,
            region_order=cfg.region_order,
            display_mode=cfg.display_mode,
            show_new_section=cfg.show_new_section,
        )
        notification_adapter = NotificationRenderAdapter(
            notification_channels=cfg._get_render_notification_channels(),
            get_time_func=cfg.get_time,
            region_order=cfg.region_order,
            display_mode=cfg.display_mode,
            rank_threshold=cfg.rank_threshold,
            batch_size=cfg.message_batch_size,
            show_new_section=cfg.show_new_section,
        )
        return RenderService(
            html_adapter=html_adapter,
            notification_adapter=notification_adapter,
            display_mode=cfg.display_mode,
            rank_threshold=cfg.rank_threshold,
            weight_config=cfg.weight_config,
        )

    def create_delivery_service(self) -> DeliveryService:
        generic_webhook_adapter = GenericWebhookDeliveryAdapter(self.runtime.config_view.config)
        return DeliveryService(generic_webhook_adapter=generic_webhook_adapter)


class WorkflowRuntimeFacade:
    """Own stateful runtime services created from the config view."""

    def __init__(self, config_view: AppConfigView):
        self.config_view = config_view
        self._storage_manager: StorageManager | None = None
        self._scheduler: Scheduler | None = None
        self._service_factory: ServiceFactory | None = None

    @property
    def service_factory(self) -> ServiceFactory:
        if self._service_factory is None:
            self._service_factory = ServiceFactory(self)
        return self._service_factory

    def get_storage_manager(self) -> StorageManager:
        if self._storage_manager is None:
            cfg = self.config_view
            self._storage_manager = get_storage_manager(
                backend_type=cfg.storage_backend_type,
                data_dir=str(cfg.get_data_dir()),
                enable_txt=bool(cfg.storage_formats.get("TXT", True)),
                enable_html=bool(cfg.storage_formats.get("HTML", True)),
                local_retention_days=cfg.storage_retention_days,
                timezone=cfg.timezone,
            )
        return self._storage_manager

    def is_first_crawl(self) -> bool:
        return self.get_storage_manager().is_first_crawl_today()

    def create_scheduler(self) -> Scheduler:
        if self._scheduler is None:
            cfg = self.config_view
            self._scheduler = Scheduler(
                schedule_config=cfg.config.get("SCHEDULE", {}),
                timeline_data=cfg.config.get("_TIMELINE_DATA", {}),
                storage_backend=self.get_storage_manager(),
                get_time_func=cfg.get_time,
                fallback_report_mode=cfg.default_report_mode,
            )
        return self._scheduler

    def create_snapshot_service(self) -> SnapshotService:
        return self.service_factory.create_snapshot_service()

    def create_selection_service(self) -> SelectionService:
        return self.service_factory.create_selection_service()

    def create_insight_service(self) -> InsightService:
        return self.service_factory.create_insight_service()

    def create_report_assembler(self) -> ReportPackageAssembler:
        return self.service_factory.create_report_assembler()

    def create_render_service(self) -> RenderService:
        return self.service_factory.create_render_service()

    def create_delivery_service(self) -> DeliveryService:
        return self.service_factory.create_delivery_service()

    @staticmethod
    def _build_noop_insight_result(
        reason: str,
        *,
        report_mode: str,
        schedule: Optional[ResolvedSchedule] = None,
    ) -> InsightResult:
        diagnostics = {
            "report_mode": report_mode,
            "skipped": True,
            "reason": reason,
        }
        if schedule is not None:
            diagnostics["schedule_analyze"] = schedule.analyze
            diagnostics["schedule_period"] = schedule.period_key
        return InsightResult(
            enabled=False,
            strategy="noop",
            diagnostics=diagnostics,
        )

    @staticmethod
    def _is_successful_insight_result(insight: InsightResult) -> bool:
        diagnostics = dict(insight.diagnostics or {})
        return (
            insight.enabled
            and bool(insight.sections)
            and not bool(diagnostics.get("skipped"))
            and not bool(diagnostics.get("error"))
            and not bool(diagnostics.get("parse_error"))
        )

    def run_selection_stage(
        self,
        *,
        mode: str,
        strategy: Optional[str] = None,
        frequency_file: Optional[str] = None,
        interests_file: Optional[str] = None,
        snapshot_service: Optional[SnapshotService] = None,
        selection_service: Optional[SelectionService] = None,
    ) -> Tuple[HotlistSnapshot, SelectionResult]:
        cfg = self.config_view
        snapshot_builder = snapshot_service or self.create_snapshot_service()
        selection_runner = selection_service or self.create_selection_service()
        snapshot = snapshot_builder.build(SnapshotOptions(mode=mode))
        options = cfg.build_selection_options(
            strategy=strategy,
            frequency_file=frequency_file,
            interests_file=interests_file,
        )
        selection = selection_runner.run(snapshot, options)
        return snapshot, selection

    def run_insight_stage(
        self,
        *,
        report_mode: str,
        snapshot: Optional[HotlistSnapshot] = None,
        selection: Optional[SelectionResult] = None,
        strategy: Optional[str] = None,
        frequency_file: Optional[str] = None,
        interests_file: Optional[str] = None,
        schedule: Optional[ResolvedSchedule] = None,
        selection_service: Optional[SelectionService] = None,
        insight_service: Optional[InsightService] = None,
    ) -> InsightResult:
        cfg = self.config_view
        options = cfg.build_insight_options(report_mode=report_mode)
        if not options.enabled or options.strategy == "noop":
            return self._build_noop_insight_result("insight stage disabled", report_mode=report_mode, schedule=schedule)

        if schedule is not None:
            if not schedule.analyze:
                return self._build_noop_insight_result(
                    "insight stage disabled by schedule",
                    report_mode=report_mode,
                    schedule=schedule,
                )

            if schedule.once_analyze and schedule.period_key:
                date_str = cfg.format_date()
                if self.get_storage_manager().has_period_executed(date_str, schedule.period_key, "analyze"):
                    return self._build_noop_insight_result(
                        f"insight stage already executed for {schedule.period_name or schedule.period_key}",
                        report_mode=report_mode,
                        schedule=schedule,
                    )

        selection_mode = options.mode
        if snapshot is None or selection is None:
            snapshot, selection = self.run_selection_stage(
                mode=selection_mode,
                strategy=cfg.filter_method if strategy is None else strategy,
                frequency_file=frequency_file,
                interests_file=interests_file,
                selection_service=selection_service,
            )

        runner = insight_service or self.create_insight_service()
        insight = runner.run(snapshot, selection, options)

        if self._is_successful_insight_result(insight) and schedule is not None and schedule.once_analyze and schedule.period_key:
            self.get_storage_manager().record_period_execution(cfg.format_date(), schedule.period_key, "analyze")

        return insight

    def assemble_report_package(
        self,
        snapshot: HotlistSnapshot,
        selection: SelectionResult,
        insight: InsightResult,
        *,
        report_assembler: Optional[ReportPackageAssembler] = None,
    ) -> ReportPackage:
        assembler = report_assembler or self.create_report_assembler()
        return assembler.assemble(snapshot, selection, insight)

    def run_render_stage(
        self,
        report: ReportPackage,
        *,
        emit_html: Optional[bool] = None,
        emit_notification: Optional[bool] = None,
        display_regions: Optional[List[str]] = None,
        update_info: Optional[Dict[str, Any]] = None,
        render_service: Optional[RenderService] = None,
    ):
        options = self.config_view.build_render_options(
            emit_html=emit_html,
            emit_notification=emit_notification,
            display_regions=display_regions,
            update_info=update_info,
        )
        service = render_service or self.create_render_service()
        return service.run(report, options)

    def run_delivery_stage(
        self,
        payloads,
        *,
        enabled: Optional[bool] = None,
        channels: Optional[List[str]] = None,
        dry_run: bool = False,
        proxy_url: Optional[str] = None,
        delivery_service: Optional[DeliveryService] = None,
    ):
        options = self.config_view.build_delivery_options(
            enabled=enabled,
            channels=channels,
            dry_run=dry_run,
            proxy_url=proxy_url,
        )
        service = delivery_service or self.create_delivery_service()
        return service.run(payloads, options)

    def cleanup(self) -> None:
        if self._storage_manager:
            self._storage_manager.cleanup_old_data()
            self._storage_manager.cleanup()
            self._storage_manager = None


class AppContext:
    """Backward-compatible facade over config and runtime services."""

    def __init__(self, config: Dict[str, Any]):
        self._config_view = AppConfigView(config)
        self._runtime = WorkflowRuntimeFacade(self._config_view)

    def __getattr__(self, name: str) -> Any:
        for target in (self._config_view, self._runtime):
            try:
                return getattr(target, name)
            except AttributeError:
                continue
        raise AttributeError(f"{type(self).__name__!s} object has no attribute {name!r}")

    @property
    def _raw_config(self) -> Dict[str, Any]:
        return self._config_view._raw_config

    @property
    def _storage_manager(self) -> StorageManager | None:
        return self._runtime._storage_manager

    @_storage_manager.setter
    def _storage_manager(self, value: StorageManager | None) -> None:
        self._runtime._storage_manager = value

    @property
    def _scheduler(self) -> Scheduler | None:
        return self._runtime._scheduler

    @_scheduler.setter
    def _scheduler(self, value: Scheduler | None) -> None:
        self._runtime._scheduler = value

    @property
    def _service_factory(self) -> ServiceFactory | None:
        return self._runtime._service_factory

    @_service_factory.setter
    def _service_factory(self, value: ServiceFactory | None) -> None:
        self._runtime._service_factory = value
