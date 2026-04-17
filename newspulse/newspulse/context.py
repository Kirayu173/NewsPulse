# coding=utf-8
"""Application context helpers."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from newspulse.ai import AIAnalysisResult
from newspulse.core.scheduler import ResolvedSchedule
from newspulse.core import (
    Scheduler,
    count_word_frequency,
    detect_latest_new_titles,
    load_frequency_words,
    matches_word_groups,
    read_all_today_titles,
)
from newspulse.notification import NotificationDispatcher, split_content_into_batches
from newspulse.report import generate_html_report, prepare_report_data, render_html_content
from newspulse.storage import get_storage_manager
from newspulse.workflow.delivery import DeliveryService, GenericWebhookDeliveryAdapter
from newspulse.workflow.insight import InsightService, to_ai_analysis_result
from newspulse.workflow.localization import LocalizationService
from newspulse.workflow.render import HTMLRenderAdapter, HotlistReportAssembler, NotificationRenderAdapter, RenderService
from newspulse.utils.time import (
    DEFAULT_TIMEZONE,
    convert_time_for_display,
    format_date_folder,
    format_time_filename,
    get_configured_time,
    get_current_time_display,
)
from newspulse.workflow.selection import SelectionService
from newspulse.workflow.shared.contracts import HotlistSnapshot, InsightResult, LocalizedReport, RenderableReport, SelectionResult
from newspulse.workflow.shared.options import (
    DeliveryOptions,
    InsightOptions,
    LocalizationOptions,
    LocalizationScope,
    RenderOptions,
    SelectionAIOptions,
    SelectionOptions,
    SnapshotOptions,
)
from newspulse.workflow.snapshot import SnapshotService


class AppContext:
    """Thin runtime facade around config, storage and report helpers."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._storage_manager = None
        self._scheduler = None

    @property
    def timezone(self) -> str:
        return self.config.get("TIMEZONE", DEFAULT_TIMEZONE)

    @property
    def rank_threshold(self) -> int:
        return self.config.get("RANK_THRESHOLD", 50)

    @property
    def weight_config(self) -> Dict[str, Any]:
        return self.config.get("WEIGHT_CONFIG", {})

    @property
    def platforms(self) -> List[Dict[str, Any]]:
        return self.config.get("PLATFORMS", [])

    @property
    def platform_ids(self) -> List[str]:
        return [platform.get("id", "") for platform in self.platforms if platform.get("id")]

    @property
    def display_mode(self) -> str:
        return self.config.get("DISPLAY_MODE", "keyword")

    @property
    def show_new_section(self) -> bool:
        return self.config.get("DISPLAY", {}).get("REGIONS", {}).get("NEW_ITEMS", True)

    @property
    def region_order(self) -> List[str]:
        return self.config.get(
            "DISPLAY", {}
        ).get("REGION_ORDER", ["hotlist", "new_items", "standalone", "ai_analysis"])

    @property
    def filter_method(self) -> str:
        return self.config.get("FILTER", {}).get("METHOD", "keyword")

    @property
    def ai_priority_sort_enabled(self) -> bool:
        return self.config.get("FILTER", {}).get("PRIORITY_SORT_ENABLED", False)

    @property
    def ai_filter_config(self) -> Dict[str, Any]:
        return self.config.get("AI_FILTER", {})

    @property
    def ai_analysis_model_config(self) -> Dict[str, Any]:
        return self.config.get("AI_ANALYSIS_MODEL", self.config.get("AI", {}))

    @property
    def ai_translation_model_config(self) -> Dict[str, Any]:
        return self.config.get("AI_TRANSLATION_MODEL", self.config.get("AI", {}))

    @property
    def ai_filter_model_config(self) -> Dict[str, Any]:
        return self.config.get("AI_FILTER_MODEL", self.config.get("AI", {}))

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

    @staticmethod
    def convert_time_display(time_str: str) -> str:
        return convert_time_for_display(time_str)

    def get_storage_manager(self):
        if self._storage_manager is None:
            self._storage_manager = get_storage_manager(
                backend_type=self.config.get("STORAGE", {}).get("BACKEND", "local"),
                data_dir=str(self.get_data_dir()),
                enable_txt=self.config.get("STORAGE", {}).get("FORMATS", {}).get("TXT", True),
                enable_html=self.config.get("STORAGE", {}).get("FORMATS", {}).get("HTML", True),
                local_retention_days=self.config.get("STORAGE", {}).get("LOCAL", {}).get("RETENTION_DAYS", 0),
                timezone=self.timezone,
            )
        return self._storage_manager

    def get_data_dir(self) -> Path:
        storage_config = self.config.get("STORAGE", {})
        local_config = storage_config.get("LOCAL", {})
        return Path(local_config.get("DATA_DIR", "output"))

    def get_output_path(self, subfolder: str, filename: str) -> str:
        output_dir = self.get_data_dir() / subfolder / self.format_date()
        output_dir.mkdir(parents=True, exist_ok=True)
        return str(output_dir / filename)

    def read_today_titles(self, platform_ids: Optional[List[str]] = None, quiet: bool = False) -> Tuple[Dict, Dict, Dict]:
        return read_all_today_titles(self.get_storage_manager(), platform_ids, quiet=quiet)

    def detect_new_titles(self, platform_ids: Optional[List[str]] = None, quiet: bool = False) -> Dict:
        return detect_latest_new_titles(self.get_storage_manager(), platform_ids, quiet=quiet)

    def is_first_crawl(self) -> bool:
        return self.get_storage_manager().is_first_crawl_today()

    def load_frequency_words(self, frequency_file: Optional[str] = None) -> Tuple[List[Dict], List[str], List[str]]:
        return load_frequency_words(frequency_file, config_root=self.config_root)

    def matches_word_groups(
        self,
        title: str,
        word_groups: List[Dict],
        filter_words: List[str],
        global_filters: Optional[List[str]] = None,
    ) -> bool:
        return matches_word_groups(title, word_groups, filter_words, global_filters)

    def count_frequency(
        self,
        results: Dict,
        word_groups: List[Dict],
        filter_words: List[str],
        id_to_name: Dict,
        title_info: Optional[Dict] = None,
        new_titles: Optional[Dict] = None,
        mode: str = "daily",
        global_filters: Optional[List[str]] = None,
        quiet: bool = False,
    ) -> Tuple[List[Dict], int]:
        return count_word_frequency(
            results=results,
            word_groups=word_groups,
            filter_words=filter_words,
            id_to_name=id_to_name,
            title_info=title_info,
            rank_threshold=self.rank_threshold,
            new_titles=new_titles,
            mode=mode,
            global_filters=global_filters,
            weight_config=self.weight_config,
            max_news_per_keyword=self.config.get("MAX_NEWS_PER_KEYWORD", 0),
            sort_by_position_first=self.config.get("SORT_BY_POSITION_FIRST", False),
            is_first_crawl_func=self.is_first_crawl,
            convert_time_func=self.convert_time_display,
            quiet=quiet,
        )

    def prepare_report(
        self,
        stats: List[Dict],
        failed_ids: Optional[List] = None,
        new_titles: Optional[Dict] = None,
        id_to_name: Optional[Dict] = None,
        mode: str = "daily",
        frequency_file: Optional[str] = None,
    ) -> Dict:
        return prepare_report_data(
            stats=stats,
            failed_ids=failed_ids,
            new_titles=new_titles,
            id_to_name=id_to_name,
            mode=mode,
            rank_threshold=self.rank_threshold,
            matches_word_groups_func=self.matches_word_groups,
            load_frequency_words_func=lambda: self.load_frequency_words(frequency_file),
            show_new_section=self.show_new_section,
        )

    def generate_html(
        self,
        stats: List[Dict],
        total_titles: int,
        failed_ids: Optional[List] = None,
        new_titles: Optional[Dict] = None,
        id_to_name: Optional[Dict] = None,
        mode: str = "daily",
        update_info: Optional[Dict] = None,
        ai_analysis: Optional[Any] = None,
        standalone_data: Optional[Dict] = None,
        frequency_file: Optional[str] = None,
    ) -> str:
        return generate_html_report(
            stats=stats,
            total_titles=total_titles,
            failed_ids=failed_ids,
            new_titles=new_titles,
            id_to_name=id_to_name,
            mode=mode,
            update_info=update_info,
            rank_threshold=self.rank_threshold,
            output_dir=str(self.get_data_dir()),
            date_folder=self.format_date(),
            time_filename=self.format_time(),
            render_html_func=lambda *args, **kwargs: self.render_html(
                *args,
                ai_analysis=ai_analysis,
                standalone_data=standalone_data,
                **kwargs,
            ),
            matches_word_groups_func=self.matches_word_groups,
            load_frequency_words_func=lambda: self.load_frequency_words(frequency_file),
        )

    def render_html(
        self,
        report_data: Dict,
        total_titles: int,
        mode: str = "daily",
        update_info: Optional[Dict] = None,
        ai_analysis: Optional[Any] = None,
        standalone_data: Optional[Dict] = None,
    ) -> str:
        return render_html_content(
            report_data=report_data,
            total_titles=total_titles,
            mode=mode,
            update_info=update_info,
            region_order=self.region_order,
            get_time_func=self.get_time,
            display_mode=self.display_mode,
            ai_analysis=ai_analysis,
            show_new_section=self.show_new_section,
            standalone_data=standalone_data,
        )

    def split_content(
        self,
        report_data: Dict,
        format_type: str,
        update_info: Optional[Dict] = None,
        max_bytes: Optional[int] = None,
        mode: str = "daily",
        ai_content: Optional[str] = None,
        standalone_data: Optional[Dict] = None,
        ai_stats: Optional[Dict] = None,
        report_type: str = "热点分析报告",
    ) -> List[str]:
        return split_content_into_batches(
            report_data=report_data,
            format_type=format_type,
            update_info=update_info,
            max_bytes=max_bytes,
            mode=mode,
            batch_sizes={"default": self.config.get("MESSAGE_BATCH_SIZE", 4000)},
            region_order=self.region_order,
            get_time_func=self.get_time,
            timezone=self.timezone,
            display_mode=self.display_mode,
            ai_content=ai_content,
            standalone_data=standalone_data,
            rank_threshold=self.rank_threshold,
            ai_stats=ai_stats,
            report_type=report_type,
            show_new_section=self.show_new_section,
        )

    def create_notification_dispatcher(self) -> NotificationDispatcher:
        return NotificationDispatcher(
            config=self.config,
            split_content_func=self.split_content,
        )

    def create_scheduler(self) -> Scheduler:
        if self._scheduler is None:
            self._scheduler = Scheduler(
                schedule_config=self.config.get("SCHEDULE", {}),
                timeline_data=self.config.get("_TIMELINE_DATA", {}),
                storage_backend=self.get_storage_manager(),
                get_time_func=self.get_time,
                fallback_report_mode=self.config.get("REPORT_MODE", "current"),
            )
        return self._scheduler

    def create_snapshot_service(self) -> SnapshotService:
        """Create the workflow snapshot builder for the current runtime."""

        standalone_config = self.config.get("DISPLAY", {}).get("STANDALONE", {})
        platform_names = {
            platform.get("id", ""): platform.get("name", platform.get("id", ""))
            for platform in self.platforms
            if platform.get("id")
        }
        return SnapshotService(
            self.get_storage_manager(),
            platform_ids=self.platform_ids,
            platform_names=platform_names,
            standalone_platform_ids=standalone_config.get("PLATFORMS", []),
            standalone_max_items=standalone_config.get("MAX_ITEMS", 20),
        )

    def create_selection_service(self) -> SelectionService:
        """Create the workflow selection service with the current project config."""

        return SelectionService(
            config_root=str(self.config_root),
            rank_threshold=self.rank_threshold,
            weight_config=self.weight_config,
            max_news_per_keyword=self.config.get("MAX_NEWS_PER_KEYWORD", 0),
            sort_by_position_first=self.config.get("SORT_BY_POSITION_FIRST", False),
            storage_manager=self.get_storage_manager(),
            ai_runtime_config=self.ai_filter_model_config,
            ai_filter_config=self.ai_filter_config,
            debug=bool(self.config.get("DEBUG", False)),
        )

    def build_selection_options(
        self,
        *,
        strategy: Optional[str] = None,
        frequency_file: Optional[str] = None,
        interests_file: Optional[str] = None,
    ) -> SelectionOptions:
        """Build workflow selection options from the current app config."""

        ai_filter_config = self.ai_filter_config
        filter_config = self.config.get("FILTER", {})
        effective_interests_file = interests_file or ai_filter_config.get("INTERESTS_FILE") or "ai_interests.txt"
        return SelectionOptions(
            strategy=strategy or self.filter_method,
            frequency_file=frequency_file or filter_config.get("FREQUENCY_FILE"),
            priority_sort_enabled=self.ai_priority_sort_enabled,
            ai=SelectionAIOptions(
                interests_file=effective_interests_file,
                batch_size=int(ai_filter_config.get("BATCH_SIZE", 200) or 200),
                batch_interval=float(ai_filter_config.get("BATCH_INTERVAL", 5) or 0),
                min_score=float(ai_filter_config.get("MIN_SCORE", 0) or 0),
                fallback_to_keyword=bool(ai_filter_config.get("FALLBACK_TO_KEYWORD", True)),
            ),
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
        """Run the native selection stage and optionally fall back to keyword mode."""

        snapshot_builder = snapshot_service or self.create_snapshot_service()
        selection_runner = selection_service or self.create_selection_service()
        snapshot = snapshot_builder.build(SnapshotOptions(mode=mode))
        options = self.build_selection_options(
            strategy=strategy,
            frequency_file=frequency_file,
            interests_file=interests_file,
        )

        try:
            selection = selection_runner.run(snapshot, options)
        except Exception as exc:
            if options.strategy == "ai" and options.ai.fallback_to_keyword:
                fallback_options = self.build_selection_options(
                    strategy="keyword",
                    frequency_file=frequency_file,
                )
                selection = selection_runner.run(snapshot, fallback_options)
                selection.diagnostics.update(
                    {
                        "requested_strategy": "ai",
                        "fallback_strategy": "keyword",
                        "fallback_reason": f"{type(exc).__name__}: {exc}",
                    }
                )
            else:
                raise

        selection.diagnostics.setdefault("requested_strategy", options.strategy)
        return snapshot, selection

    def create_insight_service(self) -> InsightService:
        """Create the workflow insight service with the current project config."""

        return InsightService(
            ai_runtime_config=self.ai_analysis_model_config,
            ai_analysis_config=self.config.get("AI_ANALYSIS", {}),
            config_root=str(self.config_root),
        )

    def create_report_assembler(self) -> HotlistReportAssembler:
        """Create the renderable report assembler for the current project config."""

        return HotlistReportAssembler(
            display_regions=self.region_order,
            timezone=self.timezone,
            display_mode=self.display_mode,
        )

    def create_localization_service(self) -> LocalizationService:
        """Create the workflow localization service with the current project config."""

        return LocalizationService(
            ai_translation_config=self.config.get("AI_TRANSLATION", {}),
            ai_runtime_config=self.ai_translation_model_config,
        )

    def create_render_service(self) -> RenderService:
        """Create the workflow render service with the current project config."""

        html_adapter = HTMLRenderAdapter(
            output_dir=str(self.get_data_dir()),
            get_time_func=self.get_time,
            date_folder_func=self.format_date,
            time_filename_func=self.format_time,
            region_order=self.region_order,
            display_mode=self.display_mode,
            show_new_section=self.show_new_section,
        )
        notification_adapter = NotificationRenderAdapter(
            notification_channels=self._get_render_notification_channels(),
            get_time_func=self.get_time,
            region_order=self.region_order,
            display_mode=self.display_mode,
            rank_threshold=self.rank_threshold,
            batch_size=self.config.get("MESSAGE_BATCH_SIZE", 4000),
            show_new_section=self.show_new_section,
        )
        return RenderService(
            html_adapter=html_adapter,
            notification_adapter=notification_adapter,
            display_mode=self.display_mode,
            rank_threshold=self.rank_threshold,
            weight_config=self.weight_config,
        )

    def create_delivery_service(self) -> DeliveryService:
        """Create the workflow delivery service with the current project config."""

        generic_webhook_adapter = GenericWebhookDeliveryAdapter(self.config)
        return DeliveryService(generic_webhook_adapter=generic_webhook_adapter)

    def build_insight_options(
        self,
        *,
        report_mode: str,
    ) -> InsightOptions:
        """Build workflow insight options from the current app config."""

        analysis_config = self.config.get("AI_ANALYSIS", {})
        enabled = bool(analysis_config.get("ENABLED", False))
        configured_strategy = str(analysis_config.get("STRATEGY", "ai" if enabled else "noop") or ("ai" if enabled else "noop")).strip()
        requested_mode = str(analysis_config.get("MODE", "follow_report") or "follow_report").strip()
        effective_mode = requested_mode if requested_mode in {"daily", "current", "incremental"} else report_mode

        return InsightOptions(
            enabled=enabled,
            strategy=configured_strategy or ("ai" if enabled else "noop"),
            mode=effective_mode,
            max_items=int(analysis_config.get("MAX_NEWS_FOR_ANALYSIS", 50) or 50),
            include_standalone=bool(analysis_config.get("INCLUDE_STANDALONE", False)),
            include_rank_timeline=bool(analysis_config.get("INCLUDE_RANK_TIMELINE", False)),
            metadata={
                "requested_mode": requested_mode,
                "report_mode": report_mode,
            },
        )

    def build_localization_options(
        self,
        *,
        strategy: Optional[str] = None,
    ) -> LocalizationOptions:
        """Build workflow localization options from the current app config."""

        translation_config = self.config.get("AI_TRANSLATION", {})
        enabled = bool(translation_config.get("ENABLED", False))
        scope = translation_config.get("SCOPE", {})
        hotlist_scope = bool(scope.get("HOTLIST", True))
        new_items_scope = bool(scope.get("NEW_ITEMS", hotlist_scope))

        return LocalizationOptions(
            enabled=enabled,
            strategy=strategy or str(translation_config.get("STRATEGY", "ai" if enabled else "noop") or ("ai" if enabled else "noop")),
            language=str(translation_config.get("LANGUAGE", "English")),
            scope=LocalizationScope(
                selection_titles=hotlist_scope,
                new_items=new_items_scope,
                standalone=bool(scope.get("STANDALONE", True)),
                insight_sections=bool(scope.get("INSIGHT", False)),
            ),
            metadata={
                "legacy_scope": dict(scope),
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
        """Build workflow render options from the current app config."""

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
        """Build workflow delivery options from the current app config."""

        effective_channels = list(channels or self._get_render_notification_channels())
        metadata: Dict[str, Any] = {}
        if proxy_url:
            metadata["proxy_url"] = proxy_url

        return DeliveryOptions(
            enabled=bool(self.config.get("ENABLE_NOTIFICATION", True)) if enabled is None else enabled,
            channels=effective_channels,
            dry_run=dry_run,
            metadata=metadata,
        )

    @staticmethod
    def _build_noop_insight_result(reason: str, *, report_mode: str, schedule: Optional[ResolvedSchedule] = None) -> InsightResult:
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
    ) -> Tuple[InsightResult, Optional[AIAnalysisResult]]:
        """Run the native insight stage and adapt the result for the current render pipeline."""

        options = self.build_insight_options(report_mode=report_mode)
        if not options.enabled or options.strategy == "noop":
            return self._build_noop_insight_result("insight stage disabled", report_mode=report_mode, schedule=schedule), None

        if schedule is not None:
            if not schedule.analyze:
                return self._build_noop_insight_result("insight stage disabled by schedule", report_mode=report_mode, schedule=schedule), None

            if schedule.once_analyze and schedule.period_key:
                date_str = self.format_date()
                if self.get_storage_manager().has_period_executed(date_str, schedule.period_key, "analyze"):
                    return (
                        self._build_noop_insight_result(
                            f"insight stage already executed for {schedule.period_name or schedule.period_key}",
                            report_mode=report_mode,
                            schedule=schedule,
                        ),
                        None,
                    )

        selection_mode = options.mode
        if snapshot is None or selection is None or selection_mode != report_mode:
            snapshot, selection = self.run_selection_stage(
                mode=selection_mode,
                strategy=self.filter_method if strategy is None else strategy,
                frequency_file=frequency_file,
                interests_file=interests_file,
                selection_service=selection_service,
            )

        runner = insight_service or self.create_insight_service()
        insight = runner.run(snapshot, selection, options)
        legacy_result = to_ai_analysis_result(
            insight,
            total_news=selection.total_selected,
            analyzed_news=int(insight.diagnostics.get("analyzed_items", 0) or 0),
            max_news_limit=options.max_items,
            hotlist_count=selection.total_selected,
            ai_mode=options.mode,
        )

        if legacy_result and legacy_result.success and schedule is not None and schedule.once_analyze and schedule.period_key:
            self.get_storage_manager().record_period_execution(self.format_date(), schedule.period_key, "analyze")

        return insight, legacy_result

    def assemble_renderable_report(
        self,
        snapshot: HotlistSnapshot,
        selection: SelectionResult,
        insight: InsightResult,
        *,
        report_assembler: Optional[HotlistReportAssembler] = None,
    ) -> RenderableReport:
        """Assemble a render-ready workflow report from native stage outputs."""

        assembler = report_assembler or self.create_report_assembler()
        return assembler.assemble(snapshot, selection, insight)

    def run_localization_stage(
        self,
        report: RenderableReport,
        *,
        strategy: Optional[str] = None,
        localization_service: Optional[LocalizationService] = None,
    ) -> LocalizedReport:
        """Run the native localization stage for the assembled renderable report."""

        options = self.build_localization_options(strategy=strategy)
        service = localization_service or self.create_localization_service()
        return service.run(report, options)

    def run_render_stage(
        self,
        report: LocalizedReport,
        *,
        emit_html: Optional[bool] = None,
        emit_notification: Optional[bool] = None,
        display_regions: Optional[List[str]] = None,
        update_info: Optional[Dict[str, Any]] = None,
        render_service: Optional[RenderService] = None,
    ):
        """Run the native render stage for the localized report."""

        options = self.build_render_options(
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
        """Run the native delivery stage for prepared payloads."""

        options = self.build_delivery_options(
            enabled=enabled,
            channels=channels,
            dry_run=dry_run,
            proxy_url=proxy_url,
        )
        service = delivery_service or self.create_delivery_service()
        return service.run(payloads, options)

    def _get_render_notification_channels(self) -> List[str]:
        channels: List[str] = []
        if self.config.get("GENERIC_WEBHOOK_URL"):
            channels.append("generic_webhook")
        return channels

    def convert_selection_to_report_data(self, selection_result: SelectionResult) -> List[Dict]:
        """Adapt native workflow selection output back into the current legacy stats structure."""

        return SelectionService.to_legacy_stats(
            selection_result,
            display_mode=self.display_mode,
            rank_threshold=self.rank_threshold,
            weight_config=self.weight_config,
        )

    def cleanup(self):
        if self._storage_manager:
            self._storage_manager.cleanup_old_data()
            self._storage_manager.cleanup()
            self._storage_manager = None
