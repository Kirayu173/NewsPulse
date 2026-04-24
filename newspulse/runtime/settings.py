# coding=utf-8
"""Typed runtime settings assembled from normalized config."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from newspulse.core.runtime_config import (
    DEFAULT_REGION_ORDER,
    REGION_FLAG_DEFAULTS,
    REGION_FLAG_KEYS,
    normalize_runtime_config,
)
from newspulse.crawler import CrawlSourceSpec
from newspulse.crawler.source_names import resolve_source_display_name
from newspulse.utils.time import DEFAULT_TIMEZONE, format_date_folder, format_time_filename, get_configured_time
from newspulse.workflow.selection.ai import build_embedding_runtime_config


@dataclass(frozen=True)
class PlatformSettings:
    """One configured crawl platform."""

    id: str
    name: str


@dataclass(frozen=True)
class AppSettings:
    """Cross-cutting app settings."""

    timezone: str = DEFAULT_TIMEZONE
    default_report_mode: str = "daily"
    show_version_update: bool = False
    version_check_url: str = ""
    configs_version_check_url: str = ""
    debug_enabled: bool = False


@dataclass(frozen=True)
class CrawlerSettings:
    """Crawler runtime settings."""

    enabled: bool
    request_interval_ms: int
    proxy_enabled: bool
    default_proxy_url: str
    platforms: tuple[PlatformSettings, ...]

    @property
    def platform_ids(self) -> list[str]:
        return [platform.id for platform in self.platforms]

    @property
    def platform_name_map(self) -> dict[str, str]:
        return {platform.id: platform.name for platform in self.platforms}

    @property
    def crawl_source_specs(self) -> list[CrawlSourceSpec]:
        return [
            CrawlSourceSpec(source_id=platform.id, source_name=platform.name)
            for platform in self.platforms
        ]


@dataclass(frozen=True)
class StorageSettings:
    """Storage backend settings."""

    backend_type: str
    data_dir: Path
    enable_txt: bool
    enable_html: bool
    retention_days: int


@dataclass(frozen=True)
class ScheduleSettings:
    """Scheduler settings."""

    config: dict[str, Any]
    timeline_data: dict[str, Any]


@dataclass(frozen=True)
class SelectionAISettings:
    """AI selection knobs."""

    interests_file: str | None
    batch_size: int
    batch_interval: float
    min_score: float
    reclassify_threshold: float
    fallback_to_keyword: bool


@dataclass(frozen=True)
class SelectionSemanticSettings:
    """Semantic recall knobs."""

    enabled: bool
    top_k: int
    min_score: float
    direct_threshold: float


@dataclass(frozen=True)
class SelectionSettings:
    """Selection stage settings and downstream runtime mappings."""

    strategy: str
    frequency_file: str | None
    priority_sort_enabled: bool
    rank_threshold: int
    weight_config: dict[str, Any]
    max_news_per_keyword: int
    sort_by_position_first: bool
    ai: SelectionAISettings
    semantic: SelectionSemanticSettings
    filter_config: dict[str, Any]
    ai_runtime_config: dict[str, Any]

    @property
    def embedding_runtime_config(self) -> dict[str, Any]:
        return build_embedding_runtime_config(self.ai_runtime_config)


@dataclass(frozen=True)
class InsightSettings:
    """Insight stage settings and downstream runtime mappings."""

    enabled: bool
    strategy: str
    mode: str
    max_items: int
    analysis_config: dict[str, Any]
    ai_runtime_config: dict[str, Any]


@dataclass(frozen=True)
class RenderSettings:
    """Render-stage display settings."""

    display_mode: str
    region_order: tuple[str, ...]
    show_new_section: bool
    standalone_platform_ids: tuple[str, ...]
    standalone_max_items: int


@dataclass(frozen=True)
class DeliverySettings:
    """Delivery-stage settings."""

    enabled: bool
    generic_webhook_url: str
    generic_webhook_template: str
    max_accounts_per_channel: int
    message_batch_size: int

    @property
    def channels(self) -> tuple[str, ...]:
        if self.generic_webhook_url:
            return ("generic_webhook",)
        return ()

    def as_adapter_config(self) -> dict[str, Any]:
        return {
            "GENERIC_WEBHOOK_URL": self.generic_webhook_url,
            "GENERIC_WEBHOOK_TEMPLATE": self.generic_webhook_template,
            "MAX_ACCOUNTS_PER_CHANNEL": self.max_accounts_per_channel,
            "MESSAGE_BATCH_SIZE": self.message_batch_size,
        }


@dataclass(frozen=True)
class RuntimePathSettings:
    """Resolved filesystem paths."""

    config_root: Path


@dataclass(frozen=True)
class RuntimeSettings:
    """Strongly typed runtime settings."""

    app: AppSettings
    crawler: CrawlerSettings
    storage: StorageSettings
    schedule: ScheduleSettings
    selection: SelectionSettings
    insight: InsightSettings
    render: RenderSettings
    delivery: DeliverySettings
    paths: RuntimePathSettings

    @classmethod
    def from_mapping(cls, config: Mapping[str, Any] | None) -> RuntimeSettings:
        raw_config = deepcopy(dict(config or {}))
        normalized = normalize_runtime_config(raw_config, raw_config=raw_config)

        platforms = tuple(
            PlatformSettings(
                id=source_id,
                name=resolve_source_display_name(source_id, str(platform.get("name", "") or "")),
            )
            for platform in normalized.get("PLATFORMS", [])
            if isinstance(platform, dict)
            for source_id in [str(platform.get("id", "") or "").strip()]
            if source_id
        )

        storage_config = normalized.get("STORAGE", {}) if isinstance(normalized, dict) else {}
        storage_formats = storage_config.get("FORMATS", {}) if isinstance(storage_config, dict) else {}
        storage_local = storage_config.get("LOCAL", {}) if isinstance(storage_config, dict) else {}
        display_config = normalized.get("DISPLAY", {}) if isinstance(normalized, dict) else {}
        workflow = normalized.get("WORKFLOW", {}) if isinstance(normalized, dict) else {}
        selection_stage = workflow.get("SELECTION", {}) if isinstance(workflow, dict) else {}
        insight_stage = workflow.get("INSIGHT", {}) if isinstance(workflow, dict) else {}
        selection_ai = selection_stage.get("AI", {}) if isinstance(selection_stage, dict) else {}
        selection_semantic = selection_stage.get("SEMANTIC", {}) if isinstance(selection_stage, dict) else {}
        path_config = normalized.get("_PATHS", {}) if isinstance(normalized.get("_PATHS", {}), dict) else {}
        config_root = path_config.get("CONFIG_ROOT")
        render_regions = display_config.get("REGIONS", {}) if isinstance(display_config.get("REGIONS", {}), dict) else {}
        standalone_config = display_config.get("STANDALONE", {}) if isinstance(display_config.get("STANDALONE", {}), dict) else {}

        return cls(
            app=AppSettings(
                timezone=str(normalized.get("TIMEZONE", DEFAULT_TIMEZONE) or DEFAULT_TIMEZONE),
                default_report_mode=str(normalized.get("REPORT_MODE", "daily") or "daily"),
                show_version_update=bool(normalized.get("SHOW_VERSION_UPDATE", False)),
                version_check_url=str(normalized.get("VERSION_CHECK_URL", "") or ""),
                configs_version_check_url=str(normalized.get("CONFIGS_VERSION_CHECK_URL", "") or ""),
                debug_enabled=bool(normalized.get("DEBUG", False)),
            ),
            crawler=CrawlerSettings(
                enabled=bool(normalized.get("ENABLE_CRAWLER", True)),
                request_interval_ms=int(normalized.get("REQUEST_INTERVAL", 100) or 100),
                proxy_enabled=bool(normalized.get("USE_PROXY", False)),
                default_proxy_url=str(normalized.get("DEFAULT_PROXY", "") or ""),
                platforms=platforms,
            ),
            storage=StorageSettings(
                backend_type=str(storage_config.get("BACKEND", "local") or "local"),
                data_dir=Path(storage_local.get("DATA_DIR", "output") or "output"),
                enable_txt=bool(storage_formats.get("TXT", True)),
                enable_html=bool(storage_formats.get("HTML", True)),
                retention_days=int(storage_local.get("RETENTION_DAYS", 0) or 0),
            ),
            schedule=ScheduleSettings(
                config=dict(normalized.get("SCHEDULE", {}) or {}),
                timeline_data=dict(normalized.get("_TIMELINE_DATA", {}) or {}),
            ),
            selection=SelectionSettings(
                strategy=str(selection_stage.get("STRATEGY", "keyword") or "keyword"),
                frequency_file=selection_stage.get("FREQUENCY_FILE"),
                priority_sort_enabled=bool(selection_stage.get("PRIORITY_SORT_ENABLED", False)),
                rank_threshold=int(normalized.get("RANK_THRESHOLD", 50) or 50),
                weight_config=dict(normalized.get("WEIGHT_CONFIG", {}) or {}),
                max_news_per_keyword=int(normalized.get("MAX_NEWS_PER_KEYWORD", 0) or 0),
                sort_by_position_first=bool(normalized.get("SORT_BY_POSITION_FIRST", False)),
                ai=SelectionAISettings(
                    interests_file=selection_ai.get("INTERESTS_FILE"),
                    batch_size=int(selection_ai.get("BATCH_SIZE", 200) or 200),
                    batch_interval=float(selection_ai.get("BATCH_INTERVAL", 5) or 0),
                    min_score=float(selection_ai.get("MIN_SCORE", 0) or 0),
                    reclassify_threshold=float(selection_ai.get("RECLASSIFY_THRESHOLD", 0.6) or 0.6),
                    fallback_to_keyword=bool(selection_ai.get("FALLBACK_TO_KEYWORD", True)),
                ),
                semantic=SelectionSemanticSettings(
                    enabled=bool(selection_semantic.get("ENABLED", True)),
                    top_k=int(selection_semantic.get("TOP_K", 3) or 3),
                    min_score=float(selection_semantic.get("MIN_SCORE", 0.55) or 0.55),
                    direct_threshold=float(selection_semantic.get("DIRECT_THRESHOLD", 0.78) or 0.78),
                ),
                filter_config=dict(normalized.get("AI_FILTER", {}) or {}),
                ai_runtime_config=dict(normalized.get("AI_FILTER_MODEL", {}) or {}),
            ),
            insight=InsightSettings(
                enabled=bool(insight_stage.get("ENABLED", False)),
                strategy=str(insight_stage.get("STRATEGY", "noop") or "noop"),
                mode=str(insight_stage.get("MODE", "follow_report") or "follow_report"),
                max_items=int(insight_stage.get("MAX_ITEMS", 50) or 50),
                analysis_config=dict(normalized.get("AI_ANALYSIS", {}) or {}),
                ai_runtime_config=dict(normalized.get("AI_ANALYSIS_MODEL", {}) or {}),
            ),
            render=RenderSettings(
                display_mode=str(normalized.get("DISPLAY_MODE", "keyword") or "keyword"),
                region_order=tuple(_resolve_region_order(display_config)),
                show_new_section=bool(render_regions.get("NEW_ITEMS", True)),
                standalone_platform_ids=tuple(
                    str(platform_id)
                    for platform_id in standalone_config.get("PLATFORMS", [])
                    if str(platform_id).strip()
                ),
                standalone_max_items=int(standalone_config.get("MAX_ITEMS", 20) or 20),
            ),
            delivery=DeliverySettings(
                enabled=bool(normalized.get("ENABLE_NOTIFICATION", True)),
                generic_webhook_url=str(normalized.get("GENERIC_WEBHOOK_URL", "") or ""),
                generic_webhook_template=str(normalized.get("GENERIC_WEBHOOK_TEMPLATE", "") or ""),
                max_accounts_per_channel=int(normalized.get("MAX_ACCOUNTS_PER_CHANNEL", 3) or 3),
                message_batch_size=int(normalized.get("MESSAGE_BATCH_SIZE", 4000) or 4000),
            ),
            paths=RuntimePathSettings(
                config_root=Path(config_root) if config_root else Path("config"),
            ),
        )

    def get_time(self) -> datetime:
        return get_configured_time(self.app.timezone)

    def format_date(self) -> str:
        return format_date_folder(timezone=self.app.timezone)

    def format_time(self) -> str:
        return format_time_filename(self.app.timezone)


def _resolve_region_order(display_config: Mapping[str, Any]) -> list[str]:
    configured_order = display_config.get("REGION_ORDER")
    base_order = configured_order if isinstance(configured_order, list) and configured_order else DEFAULT_REGION_ORDER
    regions = display_config.get("REGIONS")

    if not isinstance(regions, dict) or not regions:
        normalized_defaults: list[str] = []
        for region in base_order:
            region_name = str(region or "").strip().lower()
            if region_name in REGION_FLAG_KEYS and region_name not in normalized_defaults:
                normalized_defaults.append(region_name)
        return normalized_defaults or list(DEFAULT_REGION_ORDER)

    normalized: list[str] = []
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
