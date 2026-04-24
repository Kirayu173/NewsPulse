# coding=utf-8
"""Runtime container for stateful services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from newspulse.core import Scheduler
from newspulse.runtime.settings import RuntimeSettings
from newspulse.storage import get_storage_manager
from newspulse.workflow.delivery import DeliveryService, GenericWebhookDeliveryAdapter
from newspulse.workflow.insight import InsightService
from newspulse.workflow.report import ReportPackageAssembler
from newspulse.workflow.selection import SelectionService
from newspulse.workflow.snapshot import SnapshotService

if TYPE_CHECKING:
    from newspulse.storage.manager import StorageManager
    from newspulse.workflow.render.service import RenderService


@dataclass(slots=True)
class RuntimeProviders:
    """Optional provider overrides used mainly by tests."""

    storage_factory: Callable[[RuntimeSettings], StorageManager] | None = None
    scheduler_factory: Callable[[RuntimeSettings, StorageManager], Scheduler] | None = None
    snapshot_service_factory: Callable[[RuntimeSettings, StorageManager], SnapshotService] | None = None
    selection_service_factory: Callable[[RuntimeSettings, StorageManager], SelectionService] | None = None
    insight_service_factory: Callable[[RuntimeSettings, StorageManager], InsightService] | None = None
    report_assembler_factory: Callable[[RuntimeSettings], ReportPackageAssembler] | None = None
    render_service_factory: Callable[[RuntimeSettings], RenderService] | None = None
    delivery_service_factory: Callable[[RuntimeSettings], DeliveryService] | None = None


class RuntimeContainer:
    """Create and hold stateful runtime services."""

    def __init__(self, settings: RuntimeSettings, providers: RuntimeProviders | None = None):
        self.settings = settings
        self.providers = providers or RuntimeProviders()
        self._storage: StorageManager | None = None
        self._scheduler: Scheduler | None = None

    def storage(self) -> StorageManager:
        if self._storage is None:
            factory = self.providers.storage_factory or _default_storage_factory
            self._storage = factory(self.settings)
        return self._storage

    def scheduler(self) -> Scheduler:
        if self._scheduler is None:
            factory = self.providers.scheduler_factory or _default_scheduler_factory
            self._scheduler = factory(self.settings, self.storage())
        return self._scheduler

    def snapshot_service(self) -> SnapshotService:
        factory = self.providers.snapshot_service_factory or _default_snapshot_service_factory
        return factory(self.settings, self.storage())

    def selection_service(self) -> SelectionService:
        factory = self.providers.selection_service_factory or _default_selection_service_factory
        return factory(self.settings, self.storage())

    def insight_service(self) -> InsightService:
        factory = self.providers.insight_service_factory or _default_insight_service_factory
        return factory(self.settings, self.storage())

    def report_assembler(self) -> ReportPackageAssembler:
        factory = self.providers.report_assembler_factory or _default_report_assembler_factory
        return factory(self.settings)

    def render_service(self) -> RenderService:
        factory = self.providers.render_service_factory or _default_render_service_factory
        return factory(self.settings)

    def delivery_service(self) -> DeliveryService:
        factory = self.providers.delivery_service_factory or _default_delivery_service_factory
        return factory(self.settings)

    def cleanup(self) -> None:
        if self._storage is not None:
            self._storage.cleanup_old_data()
            self._storage.cleanup()
            self._storage = None
        self._scheduler = None


def _default_storage_factory(settings: RuntimeSettings) -> StorageManager:
    return get_storage_manager(
        backend_type=settings.storage.backend_type,
        data_dir=str(settings.storage.data_dir),
        enable_txt=settings.storage.enable_txt,
        enable_html=settings.storage.enable_html,
        local_retention_days=settings.storage.retention_days,
        timezone=settings.app.timezone,
    )


def _default_scheduler_factory(settings: RuntimeSettings, storage: StorageManager) -> Scheduler:
    return Scheduler(
        schedule_config=settings.schedule.config,
        timeline_data=settings.schedule.timeline_data,
        storage_backend=storage,
        get_time_func=settings.get_time,
        fallback_report_mode=settings.app.default_report_mode,
    )


def _default_snapshot_service_factory(settings: RuntimeSettings, storage: StorageManager) -> SnapshotService:
    return SnapshotService(
        storage,
        platform_ids=settings.crawler.platform_ids,
        platform_names=settings.crawler.platform_name_map,
        standalone_platform_ids=list(settings.render.standalone_platform_ids),
        standalone_max_items=settings.render.standalone_max_items,
    )


def _default_selection_service_factory(settings: RuntimeSettings, storage: StorageManager) -> SelectionService:
    return SelectionService(
        config_root=str(settings.paths.config_root),
        rank_threshold=settings.selection.rank_threshold,
        weight_config=settings.selection.weight_config,
        max_news_per_keyword=settings.selection.max_news_per_keyword,
        sort_by_position_first=settings.selection.sort_by_position_first,
        storage_manager=storage,
        ai_runtime_config=settings.selection.ai_runtime_config,
        embedding_runtime_config=settings.selection.embedding_runtime_config,
        ai_filter_config=settings.selection.filter_config,
        debug=settings.app.debug_enabled,
    )


def _default_insight_service_factory(settings: RuntimeSettings, storage: StorageManager) -> InsightService:
    return InsightService(
        ai_runtime_config=settings.insight.ai_runtime_config,
        ai_analysis_config=settings.insight.analysis_config,
        config_root=str(settings.paths.config_root),
        storage_manager=storage,
        proxy_url=settings.crawler.default_proxy_url if settings.crawler.proxy_enabled else None,
    )


def _default_report_assembler_factory(settings: RuntimeSettings) -> ReportPackageAssembler:
    return ReportPackageAssembler(
        timezone=settings.app.timezone,
        display_mode=settings.render.display_mode,
    )


def _default_render_service_factory(settings: RuntimeSettings) -> RenderService:
    from newspulse.workflow.render.html import HTMLRenderAdapter
    from newspulse.workflow.render.notification import NotificationRenderAdapter
    from newspulse.workflow.render.service import RenderService

    html_adapter = HTMLRenderAdapter(
        output_dir=str(settings.storage.data_dir),
        get_time_func=settings.get_time,
        date_folder_func=settings.format_date,
        time_filename_func=settings.format_time,
        region_order=list(settings.render.region_order),
        display_mode=settings.render.display_mode,
        show_new_section=settings.render.show_new_section,
    )
    notification_adapter = NotificationRenderAdapter(
        notification_channels=list(settings.delivery.channels),
        get_time_func=settings.get_time,
        region_order=list(settings.render.region_order),
        display_mode=settings.render.display_mode,
        rank_threshold=settings.selection.rank_threshold,
        batch_size=settings.delivery.message_batch_size,
        show_new_section=settings.render.show_new_section,
    )
    return RenderService(
        html_adapter=html_adapter,
        notification_adapter=notification_adapter,
        display_mode=settings.render.display_mode,
        rank_threshold=settings.selection.rank_threshold,
        weight_config=settings.selection.weight_config,
    )


def _default_delivery_service_factory(settings: RuntimeSettings) -> DeliveryService:
    generic_webhook_adapter = GenericWebhookDeliveryAdapter(settings.delivery.as_adapter_config())
    return DeliveryService(generic_webhook_adapter=generic_webhook_adapter)
