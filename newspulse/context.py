# coding=utf-8
"""Application context helpers."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from newspulse.crawler import CrawlSourceSpec
from newspulse.core.scheduler import ResolvedSchedule
from newspulse.core import (
    Scheduler,
)
from newspulse.crawler.source_names import resolve_source_display_name
from newspulse.storage import get_storage_manager
from newspulse.workflow.delivery import DeliveryService, GenericWebhookDeliveryAdapter
from newspulse.workflow.insight import InsightService
from newspulse.workflow.report import ReportPackageAssembler
from newspulse.utils.time import (
    DEFAULT_TIMEZONE,
    format_date_folder,
    format_time_filename,
    get_configured_time,
    get_current_time_display,
)
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
    from newspulse.workflow.render.service import RenderService


DEFAULT_REGION_ORDER = ["hotlist", "new_items", "standalone", "insight"]
REGION_FLAG_KEYS = {
    "hotlist": "HOTLIST",
    "new_items": "NEW_ITEMS",
    "standalone": "STANDALONE",
    "insight": "INSIGHT",
}
REGION_FLAG_DEFAULTS = {
    "hotlist": True,
    "new_items": True,
    "standalone": False,
    "insight": True,
}


class ServiceFactory:
    """Centralize workflow service construction for AppContext."""

    def __init__(self, context: "AppContext"):
        self.context = context

    def create_snapshot_service(self) -> SnapshotService:
        ctx = self.context
        standalone_config = ctx.display_config.get("STANDALONE", {})
        return SnapshotService(
            ctx.get_storage_manager(),
            platform_ids=ctx.platform_ids,
            platform_names=ctx.platform_name_map,
            standalone_platform_ids=standalone_config.get("PLATFORMS", []),
            standalone_max_items=standalone_config.get("MAX_ITEMS", 20),
        )

    def create_selection_service(self) -> SelectionService:
        ctx = self.context
        return SelectionService(
            config_root=str(ctx.config_root),
            rank_threshold=ctx.rank_threshold,
            weight_config=ctx.weight_config,
            max_news_per_keyword=ctx.max_news_per_keyword,
            sort_by_position_first=ctx.sort_by_position_first,
            storage_manager=ctx.get_storage_manager(),
            ai_runtime_config=ctx.ai_filter_model_config,
            embedding_runtime_config=ctx.ai_filter_embedding_model_config,
            ai_filter_config=ctx.ai_filter_config,
            debug=ctx.debug_enabled,
        )

    def create_insight_service(self) -> InsightService:
        ctx = self.context
        return InsightService(
            ai_runtime_config=ctx.ai_analysis_model_config,
            ai_analysis_config=ctx.ai_analysis_config,
            config_root=str(ctx.config_root),
            storage_manager=ctx.get_storage_manager(),
            proxy_url=ctx.default_proxy_url if ctx.proxy_enabled else None,
        )

    def create_report_assembler(self) -> ReportPackageAssembler:
        ctx = self.context
        return ReportPackageAssembler(
            timezone=ctx.timezone,
            display_mode=ctx.display_mode,
        )

    def create_render_service(self) -> "RenderService":
        from newspulse.workflow.render.html import HTMLRenderAdapter
        from newspulse.workflow.render.notification import NotificationRenderAdapter
        from newspulse.workflow.render.service import RenderService

        ctx = self.context
        html_adapter = HTMLRenderAdapter(
            output_dir=str(ctx.get_data_dir()),
            get_time_func=ctx.get_time,
            date_folder_func=ctx.format_date,
            time_filename_func=ctx.format_time,
            region_order=ctx.region_order,
            display_mode=ctx.display_mode,
            show_new_section=ctx.show_new_section,
        )
        notification_adapter = NotificationRenderAdapter(
            notification_channels=ctx._get_render_notification_channels(),
            get_time_func=ctx.get_time,
            region_order=ctx.region_order,
            display_mode=ctx.display_mode,
            rank_threshold=ctx.rank_threshold,
            batch_size=ctx.message_batch_size,
            show_new_section=ctx.show_new_section,
        )
        return RenderService(
            html_adapter=html_adapter,
            notification_adapter=notification_adapter,
            display_mode=ctx.display_mode,
            rank_threshold=ctx.rank_threshold,
            weight_config=ctx.weight_config,
        )

    def create_delivery_service(self) -> DeliveryService:
        generic_webhook_adapter = GenericWebhookDeliveryAdapter(self.context.config)
        return DeliveryService(generic_webhook_adapter=generic_webhook_adapter)


class AppContext:
    """Thin runtime facade around config, storage and report helpers."""

    def __init__(self, config: Dict[str, Any]):
        self._raw_config = deepcopy(config) if isinstance(config, dict) else {}
        self.config = deepcopy(config) if isinstance(config, dict) else {}
        self._storage_manager = None
        self._scheduler = None
        self._service_factory: ServiceFactory | None = None
        self._normalize_config()

    @property
    def timezone(self) -> str:
        return self.config.get("TIMEZONE", DEFAULT_TIMEZONE)

    @property
    def workflow_config(self) -> Dict[str, Any]:
        workflow = self.config.get("WORKFLOW", {})
        if isinstance(workflow, dict) and workflow:
            return workflow
        workflow = self._raw_config.get("workflow", {})
        return workflow if isinstance(workflow, dict) else {}

    @property
    def raw_ai_config(self) -> Dict[str, Any]:
        ai = self._raw_config.get("ai", {})
        return ai if isinstance(ai, dict) else {}

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
        return self.config.get("DISPLAY_MODE", "keyword")

    @property
    def display_config(self) -> Dict[str, Any]:
        display = self.config.get("DISPLAY", {})
        return display if isinstance(display, dict) else {}

    @property
    def show_new_section(self) -> bool:
        return self.display_config.get("REGIONS", {}).get("NEW_ITEMS", True)

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
            flag_key = REGION_FLAG_KEYS[region_name]
            enabled = regions.get(flag_key, REGION_FLAG_DEFAULTS[region_name])
            if enabled:
                normalized.append(region_name)

        if normalized or isinstance(configured_order, list):
            return normalized
        return list(DEFAULT_REGION_ORDER)

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
        return storage if isinstance(storage, dict) else {}

    @property
    def storage_formats(self) -> Dict[str, Any]:
        formats = self.storage_config.get("FORMATS", {})
        return formats if isinstance(formats, dict) else {}

    @property
    def storage_local_config(self) -> Dict[str, Any]:
        local = self.storage_config.get("LOCAL", {})
        return local if isinstance(local, dict) else {}

    @property
    def storage_backend_type(self) -> str:
        return str(self.storage_config.get("BACKEND", "local") or "local")

    @property
    def storage_retention_days(self) -> int:
        return int(self.storage_local_config.get("RETENTION_DAYS", 0) or 0)

    @property
    def service_factory(self) -> ServiceFactory:
        if self._service_factory is None:
            self._service_factory = ServiceFactory(self)
        return self._service_factory

    @property
    def ai_filter_config(self) -> Dict[str, Any]:
        selection_ai = self.selection_stage_config.get("AI", {})
        operation = self._get_ai_operation_mapping("selection", legacy_key="AI_FILTER")
        return {
            "BATCH_SIZE": int(selection_ai.get("BATCH_SIZE", 200) or 200),
            "BATCH_INTERVAL": float(selection_ai.get("BATCH_INTERVAL", 5) or 0),
            "TIMEOUT": self._mapping_get(operation, "TIMEOUT", "timeout"),
            "NUM_RETRIES": self._mapping_get(operation, "NUM_RETRIES", "num_retries"),
            "EXTRA_PARAMS": self._coerce_mapping(
                self._mapping_get(operation, "EXTRA_PARAMS", "extra_params", default={}),
            ),
            "INTERESTS_FILE": selection_ai.get("INTERESTS_FILE"),
            "PROMPT_FILE": str(self._mapping_get(operation, "PROMPT_FILE", "prompt_file", default="prompt.txt") or "prompt.txt"),
            "EXTRACT_PROMPT_FILE": str(
                self._mapping_get(operation, "EXTRACT_PROMPT_FILE", "extract_prompt_file", default="extract_prompt.txt")
                or "extract_prompt.txt"
            ),
            "UPDATE_TAGS_PROMPT_FILE": str(
                self._mapping_get(
                    operation,
                    "UPDATE_TAGS_PROMPT_FILE",
                    "update_tags_prompt_file",
                    default="update_tags_prompt.txt",
                )
                or "update_tags_prompt.txt"
            ),
            "RECLASSIFY_THRESHOLD": float(selection_ai.get("RECLASSIFY_THRESHOLD", 0.6) or 0.6),
            "MIN_SCORE": float(selection_ai.get("MIN_SCORE", 0) or 0),
            "FALLBACK_TO_KEYWORD": bool(selection_ai.get("FALLBACK_TO_KEYWORD", True)),
        }

    @property
    def ai_analysis_config(self) -> Dict[str, Any]:
        insight = self.insight_stage_config
        operation = self._get_ai_operation_mapping("insight", legacy_key="AI_ANALYSIS")
        content = self._get_nested_mapping(insight, "CONTENT", "content")
        item_analysis = self._get_nested_mapping(insight, "ITEM_ANALYSIS", "item_analysis")
        aggregate = self._get_nested_mapping(insight, "AGGREGATE", "aggregate")
        return {
            "ENABLED": bool(insight.get("ENABLED", False)),
            "STRATEGY": str(insight.get("STRATEGY", "noop") or "noop"),
            "LANGUAGE": str(insight.get("LANGUAGE", "Chinese") or "Chinese"),
            "PROMPT_FILE": str(
                self._mapping_get(operation, "PROMPT_FILE", "prompt_file", default="ai_analysis_prompt.txt")
                or "ai_analysis_prompt.txt"
            ),
            "MODE": str(insight.get("MODE", "follow_report") or "follow_report"),
            "MAX_ITEMS": int(insight.get("MAX_ITEMS", 50) or 50),
            "TIMEOUT": self._mapping_get(operation, "TIMEOUT", "timeout"),
            "NUM_RETRIES": self._mapping_get(operation, "NUM_RETRIES", "num_retries"),
            "EXTRA_PARAMS": self._coerce_mapping(
                self._mapping_get(operation, "EXTRA_PARAMS", "extra_params", default={}),
            ),
            "ITEM_PROMPT_FILE": str(
                self._mapping_get(
                    operation,
                    "ITEM_PROMPT_FILE",
                    "item_prompt_file",
                    default="ai_insight_item_prompt.txt",
                )
                or "ai_insight_item_prompt.txt"
            ),
            "CONTENT": {
                "CACHE_ENABLED": bool(
                    self._mapping_get(content, "CACHE_ENABLED", "cache_enabled", default=True)
                ),
                "ASYNC_ENABLED": bool(
                    self._mapping_get(content, "ASYNC_ENABLED", "async_enabled", default=False)
                ),
                "MAX_CONCURRENCY": int(
                    self._mapping_get(content, "MAX_CONCURRENCY", "max_concurrency", default=8) or 8
                ),
                "REQUEST_TIMEOUT": int(
                    self._mapping_get(
                        content,
                        "REQUEST_TIMEOUT",
                        "request_timeout",
                        "TIMEOUT",
                        "timeout",
                        default=12,
                    )
                    or 12
                ),
                "TIMEOUT": int(
                    self._mapping_get(
                        content,
                        "REQUEST_TIMEOUT",
                        "request_timeout",
                        "TIMEOUT",
                        "timeout",
                        default=12,
                    )
                    or 12
                ),
                "REDUCED_CHARS": int(
                    self._mapping_get(content, "REDUCED_CHARS", "reduced_chars", default=1600) or 1600
                ),
            },
            "ITEM_ANALYSIS": {
                "MIN_EVIDENCE_SENTENCES": int(
                    self._mapping_get(
                        item_analysis,
                        "MIN_EVIDENCE_SENTENCES",
                        "min_evidence_sentences",
                        default=3,
                    )
                    or 3
                ),
                "ITEM_PROMPT_FILE": str(
                    self._mapping_get(
                        item_analysis,
                        "PROMPT_FILE",
                        "prompt_file",
                        default=(
                            self._mapping_get(
                                operation,
                                "ITEM_PROMPT_FILE",
                                "item_prompt_file",
                                default="ai_insight_item_prompt.txt",
                            )
                            or "ai_insight_item_prompt.txt"
                        ),
                    )
                    or "ai_insight_item_prompt.txt"
                ),
            },
            "AGGREGATE": {
                "PROMPT_FILE": str(
                    self._mapping_get(
                        aggregate,
                        "PROMPT_FILE",
                        "prompt_file",
                        default=(
                            self._mapping_get(operation, "PROMPT_FILE", "prompt_file", default="ai_analysis_prompt.txt")
                            or "ai_analysis_prompt.txt"
                        ),
                    )
                    or "ai_analysis_prompt.txt"
                ),
            },
        }

    @property
    def ai_analysis_model_config(self) -> Dict[str, Any]:
        configured = self.config.get("AI_ANALYSIS_MODEL", {})
        if isinstance(configured, dict) and configured:
            return configured
        return self._merge_ai_runtime_config(
            self.ai_runtime_config,
            self._get_ai_operation_mapping("insight", legacy_key="AI_ANALYSIS"),
        )

    @property
    def ai_filter_model_config(self) -> Dict[str, Any]:
        configured = self.config.get("AI_FILTER_MODEL", {})
        if isinstance(configured, dict) and configured:
            return configured
        return self._merge_ai_runtime_config(
            self.ai_runtime_config,
            self._get_ai_operation_mapping("selection", legacy_key="AI_FILTER"),
        )

    @property
    def ai_filter_embedding_model_config(self) -> Dict[str, Any]:
        return build_embedding_runtime_config(self.ai_filter_model_config)

    @property
    def ai_runtime_config(self) -> Dict[str, Any]:
        configured = self.config.get("AI", {})
        if isinstance(configured, dict) and configured:
            return configured
        return self._normalize_ai_runtime_mapping(self._get_nested_mapping(self.raw_ai_config, "RUNTIME", "runtime"))

    @property
    def config_root(self) -> Path:
        config_root = self.config.get("_PATHS", {}).get("CONFIG_ROOT")
        return Path(config_root) if config_root else Path("config")

    @property
    def selection_stage_config(self) -> Dict[str, Any]:
        workflow_selection = self._get_workflow_stage("SELECTION", "selection")
        if workflow_selection:
            workflow_ai = self._get_nested_mapping(workflow_selection, "AI", "ai")
            workflow_semantic = self._get_nested_mapping(workflow_selection, "SEMANTIC", "semantic")
            return {
                "STRATEGY": str(self._mapping_get(workflow_selection, "STRATEGY", "strategy", default="keyword") or "keyword"),
                "FREQUENCY_FILE": self._mapping_get(workflow_selection, "FREQUENCY_FILE", "frequency_file"),
                "PRIORITY_SORT_ENABLED": bool(
                    self._mapping_get(workflow_selection, "PRIORITY_SORT_ENABLED", "priority_sort_enabled", default=False)
                ),
                "AI": {
                    "INTERESTS_FILE": self._mapping_get(workflow_ai, "INTERESTS_FILE", "interests_file"),
                    "BATCH_SIZE": int(self._mapping_get(workflow_ai, "BATCH_SIZE", "batch_size", default=200) or 200),
                    "BATCH_INTERVAL": float(self._mapping_get(workflow_ai, "BATCH_INTERVAL", "batch_interval", default=5) or 0),
                    "MIN_SCORE": float(self._mapping_get(workflow_ai, "MIN_SCORE", "min_score", default=0) or 0),
                    "RECLASSIFY_THRESHOLD": float(
                        self._mapping_get(workflow_ai, "RECLASSIFY_THRESHOLD", "reclassify_threshold", default=0.6) or 0.6
                    ),
                    "FALLBACK_TO_KEYWORD": bool(
                        self._mapping_get(workflow_ai, "FALLBACK_TO_KEYWORD", "fallback_to_keyword", default=True)
                    ),
                },
                "SEMANTIC": {
                    "ENABLED": bool(
                        self._mapping_get(workflow_semantic, "ENABLED", "enabled", default=True)
                    ),
                    "TOP_K": int(self._mapping_get(workflow_semantic, "TOP_K", "top_k", default=3) or 3),
                    "MIN_SCORE": float(
                        self._mapping_get(workflow_semantic, "MIN_SCORE", "min_score", default=0.55) or 0.55
                    ),
                    "DIRECT_THRESHOLD": float(
                        self._mapping_get(
                            workflow_semantic,
                            "DIRECT_THRESHOLD",
                            "direct_threshold",
                            default=0.78,
                        )
                        or 0.78
                    ),
                },
            }

        filter_config = self.config.get("FILTER", {})
        ai_filter_config = self.config.get("AI_FILTER", {})
        return {
            "STRATEGY": str(filter_config.get("METHOD", "keyword") or "keyword"),
            "FREQUENCY_FILE": filter_config.get("FREQUENCY_FILE"),
            "PRIORITY_SORT_ENABLED": bool(filter_config.get("PRIORITY_SORT_ENABLED", False)),
            "AI": {
                "INTERESTS_FILE": ai_filter_config.get("INTERESTS_FILE"),
                "BATCH_SIZE": int(ai_filter_config.get("BATCH_SIZE", 200) or 200),
                "BATCH_INTERVAL": float(ai_filter_config.get("BATCH_INTERVAL", 5) or 0),
                "MIN_SCORE": float(ai_filter_config.get("MIN_SCORE", 0) or 0),
                "RECLASSIFY_THRESHOLD": float(ai_filter_config.get("RECLASSIFY_THRESHOLD", 0.6) or 0.6),
                "FALLBACK_TO_KEYWORD": bool(ai_filter_config.get("FALLBACK_TO_KEYWORD", True)),
            },
            "SEMANTIC": {
                "ENABLED": True,
                "TOP_K": 3,
                "MIN_SCORE": 0.55,
                "DIRECT_THRESHOLD": 0.78,
            },
        }

    @property
    def insight_stage_config(self) -> Dict[str, Any]:
        workflow_insight = self._get_workflow_stage("INSIGHT", "insight")
        if workflow_insight:
            workflow_content = self._get_nested_mapping(workflow_insight, "CONTENT", "content")
            workflow_item_analysis = self._get_nested_mapping(workflow_insight, "ITEM_ANALYSIS", "item_analysis")
            workflow_aggregate = self._get_nested_mapping(workflow_insight, "AGGREGATE", "aggregate")
            enabled = bool(self._mapping_get(workflow_insight, "ENABLED", "enabled", default=False))
            return {
                "ENABLED": enabled,
                "STRATEGY": str(
                    self._mapping_get(workflow_insight, "STRATEGY", "strategy", default="ai" if enabled else "noop")
                    or ("ai" if enabled else "noop")
                ),
                "MODE": str(self._mapping_get(workflow_insight, "MODE", "mode", default="follow_report") or "follow_report"),
                "MAX_ITEMS": int(self._mapping_get(workflow_insight, "MAX_ITEMS", "max_items", default=50) or 50),
                "LANGUAGE": str(self._mapping_get(workflow_insight, "LANGUAGE", "language", default="Chinese") or "Chinese"),
                "CONTENT": {
                    "CACHE_ENABLED": bool(
                        self._mapping_get(workflow_content, "CACHE_ENABLED", "cache_enabled", default=True)
                    ),
                    "ASYNC_ENABLED": bool(
                        self._mapping_get(workflow_content, "ASYNC_ENABLED", "async_enabled", default=False)
                    ),
                    "MAX_CONCURRENCY": int(
                        self._mapping_get(workflow_content, "MAX_CONCURRENCY", "max_concurrency", default=8) or 8
                    ),
                    "REQUEST_TIMEOUT": int(
                        self._mapping_get(
                            workflow_content,
                            "REQUEST_TIMEOUT",
                            "request_timeout",
                            "TIMEOUT",
                            "timeout",
                            default=12,
                        )
                        or 12
                    ),
                    "TIMEOUT": int(
                        self._mapping_get(
                            workflow_content,
                            "REQUEST_TIMEOUT",
                            "request_timeout",
                            "TIMEOUT",
                            "timeout",
                            default=12,
                        )
                        or 12
                    ),
                    "REDUCED_CHARS": int(
                        self._mapping_get(workflow_content, "REDUCED_CHARS", "reduced_chars", default=1600) or 1600
                    ),
                },
                "ITEM_ANALYSIS": {
                    "PROMPT_FILE": str(
                        self._mapping_get(
                            workflow_item_analysis,
                            "PROMPT_FILE",
                            "prompt_file",
                            default="ai_insight_item_prompt.txt",
                        )
                        or "ai_insight_item_prompt.txt"
                    ),
                    "MIN_EVIDENCE_SENTENCES": int(
                        self._mapping_get(
                            workflow_item_analysis,
                            "MIN_EVIDENCE_SENTENCES",
                            "min_evidence_sentences",
                            default=3,
                        )
                        or 3
                    ),
                },
                "AGGREGATE": {
                    "PROMPT_FILE": str(
                        self._mapping_get(
                            workflow_aggregate,
                            "PROMPT_FILE",
                            "prompt_file",
                            default="ai_analysis_prompt.txt",
                        )
                        or "ai_analysis_prompt.txt"
                    ),
                },
            }

        analysis_config = self.config.get("AI_ANALYSIS", {})
        enabled = bool(analysis_config.get("ENABLED", False))
        return {
            "ENABLED": enabled,
            "STRATEGY": str(analysis_config.get("STRATEGY", "ai" if enabled else "noop") or ("ai" if enabled else "noop")),
            "MODE": str(analysis_config.get("MODE", "follow_report") or "follow_report"),
            "MAX_ITEMS": int(analysis_config.get("MAX_ITEMS", 50) or 50),
            "LANGUAGE": str(analysis_config.get("LANGUAGE", "Chinese") or "Chinese"),
            "CONTENT": self._coerce_mapping(analysis_config.get("CONTENT", {})),
            "ITEM_ANALYSIS": self._coerce_mapping(analysis_config.get("ITEM_ANALYSIS", {})),
            "AGGREGATE": self._coerce_mapping(analysis_config.get("AGGREGATE", {})),
        }

    @staticmethod
    def _mapping_get(mapping: Dict[str, Any], *names: str, default: Any = None) -> Any:
        if not isinstance(mapping, dict):
            return default
        for name in names:
            if name in mapping and mapping[name] is not None:
                return mapping[name]
        return default

    @staticmethod
    def _get_nested_mapping(mapping: Dict[str, Any], *names: str) -> Dict[str, Any]:
        for name in names:
            value = mapping.get(name)
            if isinstance(value, dict):
                return value
        return {}

    @staticmethod
    def _coerce_mapping(value: Any) -> Dict[str, Any]:
        return dict(value) if isinstance(value, dict) else {}

    @classmethod
    def _normalize_ai_runtime_mapping(cls, mapping: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(mapping, dict):
            return {}

        normalized: Dict[str, Any] = {}
        for target_key, *source_keys in (
            ("MODEL", "MODEL", "model"),
            ("API_KEY", "API_KEY", "api_key"),
            ("API_BASE", "API_BASE", "api_base"),
            ("TIMEOUT", "TIMEOUT", "timeout"),
            ("TEMPERATURE", "TEMPERATURE", "temperature"),
            ("MAX_TOKENS", "MAX_TOKENS", "max_tokens"),
            ("NUM_RETRIES", "NUM_RETRIES", "num_retries"),
        ):
            value = cls._mapping_get(mapping, *source_keys)
            if value not in (None, ""):
                normalized[target_key] = value

        fallback_models = cls._mapping_get(mapping, "FALLBACK_MODELS", "fallback_models")
        if fallback_models is not None:
            normalized["FALLBACK_MODELS"] = fallback_models

        extra_params = cls._mapping_get(mapping, "EXTRA_PARAMS", "extra_params")
        if isinstance(extra_params, dict):
            normalized["EXTRA_PARAMS"] = dict(extra_params)

        return normalized

    @classmethod
    def _normalize_ai_operation_mapping(cls, mapping: Dict[str, Any]) -> Dict[str, Any]:
        normalized = cls._normalize_ai_runtime_mapping(mapping)
        if not isinstance(mapping, dict):
            return normalized

        for target_key, *source_keys in (
            ("PROMPT_FILE", "PROMPT_FILE", "prompt_file"),
            ("EXTRACT_PROMPT_FILE", "EXTRACT_PROMPT_FILE", "extract_prompt_file"),
            ("UPDATE_TAGS_PROMPT_FILE", "UPDATE_TAGS_PROMPT_FILE", "update_tags_prompt_file"),
        ):
            value = cls._mapping_get(mapping, *source_keys)
            if value not in (None, ""):
                normalized[target_key] = value
        return normalized

    @classmethod
    def _merge_ai_runtime_config(cls, base_config: Dict[str, Any], override_config: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(base_config or {})
        merged.update(cls._normalize_ai_runtime_mapping(override_config))
        return merged

    def _get_ai_operation_mapping(self, operation_name: str, *, legacy_key: str | None = None) -> Dict[str, Any]:
        operations = self._get_nested_mapping(self.raw_ai_config, "OPERATIONS", "operations")
        operation = self._get_nested_mapping(
            operations,
            operation_name,
            operation_name.lower(),
            operation_name.upper(),
        )
        merged: Dict[str, Any] = {}
        if legacy_key:
            legacy_config = self.config.get(legacy_key, {})
            if isinstance(legacy_config, dict):
                merged.update(legacy_config)
        merged.update(operation)
        merged.update(self._normalize_ai_operation_mapping(operation))
        return merged

    def _get_workflow_stage(self, *names: str) -> Dict[str, Any]:
        for name in names:
            value = self.workflow_config.get(name)
            if isinstance(value, dict) and value:
                return value
        return {}

    def _normalize_config(self) -> None:
        self.config["PLATFORMS"] = self._resolve_platforms()
        self.config["DISPLAY"] = self._resolve_display_config()
        self.config["STORAGE"] = self._resolve_storage_config()
        self.config["WORKFLOW"] = {
            "SELECTION": self.selection_stage_config,
            "INSIGHT": self.insight_stage_config,
        }
        self.config["AI"] = self.ai_runtime_config
        self.config["AI_FILTER"] = self.ai_filter_config
        self.config["AI_ANALYSIS"] = self.ai_analysis_config
        self.config["AI_FILTER_MODEL"] = self.ai_filter_model_config
        self.config["AI_ANALYSIS_MODEL"] = self.ai_analysis_model_config
        self.config["FILTER"] = {
            "METHOD": self.filter_method,
            "FREQUENCY_FILE": self.selection_stage_config.get("FREQUENCY_FILE"),
            "PRIORITY_SORT_ENABLED": self.ai_priority_sort_enabled,
        }

    def _resolve_platforms(self) -> List[Dict[str, Any]]:
        platforms = self.config.get("PLATFORMS", [])
        if isinstance(platforms, list) and platforms:
            return [dict(platform) for platform in platforms if isinstance(platform, dict)]

        legacy_platforms = self._get_nested_mapping(self._raw_config, "platforms")
        legacy_sources = legacy_platforms.get("sources", [])
        if isinstance(legacy_sources, list):
            return [dict(platform) for platform in legacy_sources if isinstance(platform, dict)]
        return []

    def _resolve_display_config(self) -> Dict[str, Any]:
        display = self.config.get("DISPLAY", {})
        if isinstance(display, dict) and display:
            return {
                "REGION_ORDER": list(display.get("REGION_ORDER", DEFAULT_REGION_ORDER)),
                "REGIONS": self._coerce_mapping(display.get("REGIONS", {})),
                "STANDALONE": self._coerce_mapping(display.get("STANDALONE", {})),
            }

        legacy_display = self._coerce_mapping(self._raw_config.get("display", {}))
        if not legacy_display:
            return {
                "REGION_ORDER": list(DEFAULT_REGION_ORDER),
                "REGIONS": {},
                "STANDALONE": {},
            }
        legacy_regions = self._coerce_mapping(legacy_display.get("regions", {}))
        legacy_standalone = self._coerce_mapping(legacy_display.get("standalone", {}))
        region_order = [
            str(region or "").strip().lower()
            for region in legacy_display.get("region_order", DEFAULT_REGION_ORDER)
            if str(region or "").strip().lower() in REGION_FLAG_KEYS
        ]
        return {
            "REGION_ORDER": region_order or list(DEFAULT_REGION_ORDER),
            "REGIONS": {
                "HOTLIST": bool(legacy_regions.get("hotlist", True)),
                "NEW_ITEMS": bool(legacy_regions.get("new_items", True)),
                "STANDALONE": bool(legacy_regions.get("standalone", False)),
                "INSIGHT": bool(legacy_regions.get("insight", True)),
            },
            "STANDALONE": {
                "PLATFORMS": list(legacy_standalone.get("platforms", [])),
                "MAX_ITEMS": int(legacy_standalone.get("max_items", 20) or 20),
            },
        }

    def _resolve_storage_config(self) -> Dict[str, Any]:
        storage = self.config.get("STORAGE", {})
        if isinstance(storage, dict) and storage:
            return {
                "BACKEND": str(storage.get("BACKEND", "local") or "local"),
                "FORMATS": self._coerce_mapping(storage.get("FORMATS", {})),
                "LOCAL": self._coerce_mapping(storage.get("LOCAL", {})),
            }

        legacy_storage = self._coerce_mapping(self._raw_config.get("storage", {}))
        legacy_formats = self._coerce_mapping(legacy_storage.get("formats", {}))
        legacy_local = self._coerce_mapping(legacy_storage.get("local", {}))
        return {
            "BACKEND": str(legacy_storage.get("backend", "local") or "local"),
            "FORMATS": {
                "SQLITE": bool(legacy_formats.get("sqlite", True)),
                "TXT": bool(legacy_formats.get("txt", True)),
                "HTML": bool(legacy_formats.get("html", True)),
            },
            "LOCAL": {
                "DATA_DIR": str(legacy_local.get("data_dir", "output") or "output"),
                "RETENTION_DAYS": int(legacy_local.get("retention_days", 0) or 0),
            },
        }

    def get_time(self) -> datetime:
        return get_configured_time(self.timezone)

    def format_date(self) -> str:
        return format_date_folder(timezone=self.timezone)

    def format_time(self) -> str:
        return format_time_filename(self.timezone)

    def get_time_display(self) -> str:
        return get_current_time_display(self.timezone)

    def get_storage_manager(self):
        if self._storage_manager is None:
            self._storage_manager = get_storage_manager(
                backend_type=self.storage_backend_type,
                data_dir=str(self.get_data_dir()),
                enable_txt=bool(self.storage_formats.get("TXT", True)),
                enable_html=bool(self.storage_formats.get("HTML", True)),
                local_retention_days=self.storage_retention_days,
                timezone=self.timezone,
            )
        return self._storage_manager

    def get_data_dir(self) -> Path:
        return Path(self.storage_local_config.get("DATA_DIR", "output"))

    def get_output_path(self, subfolder: str, filename: str) -> str:
        output_dir = self.get_data_dir() / subfolder / self.format_date()
        output_dir.mkdir(parents=True, exist_ok=True)
        return str(output_dir / filename)

    def is_first_crawl(self) -> bool:
        return self.get_storage_manager().is_first_crawl_today()

    def create_scheduler(self) -> Scheduler:
        if self._scheduler is None:
            self._scheduler = Scheduler(
                schedule_config=self.config.get("SCHEDULE", {}),
                timeline_data=self.config.get("_TIMELINE_DATA", {}),
                storage_backend=self.get_storage_manager(),
                get_time_func=self.get_time,
                fallback_report_mode=self.default_report_mode,
            )
        return self._scheduler

    def create_snapshot_service(self) -> SnapshotService:
        """Create the workflow snapshot builder for the current runtime."""

        return self.service_factory.create_snapshot_service()

    def create_selection_service(self) -> SelectionService:
        """Create the workflow selection service with the current project config."""

        return self.service_factory.create_selection_service()

    def build_selection_options(
        self,
        *,
        strategy: Optional[str] = None,
        frequency_file: Optional[str] = None,
        interests_file: Optional[str] = None,
    ) -> SelectionOptions:
        """Build workflow selection options from the current app config."""

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
        """Run the native selection stage."""

        snapshot_builder = snapshot_service or self.create_snapshot_service()
        selection_runner = selection_service or self.create_selection_service()
        snapshot = snapshot_builder.build(SnapshotOptions(mode=mode))
        options = self.build_selection_options(
            strategy=strategy,
            frequency_file=frequency_file,
            interests_file=interests_file,
        )
        selection = selection_runner.run(snapshot, options)
        return snapshot, selection

    def create_insight_service(self) -> InsightService:
        """Create the workflow insight service with the current project config."""

        return self.service_factory.create_insight_service()

    def create_report_assembler(self) -> ReportPackageAssembler:
        """Create the Stage 6 report package assembler for the current project config."""

        return self.service_factory.create_report_assembler()

    def create_render_service(self) -> RenderService:
        """Create the workflow render service with the current project config."""

        return self.service_factory.create_render_service()

    def create_delivery_service(self) -> DeliveryService:
        """Create the workflow delivery service with the current project config."""

        return self.service_factory.create_delivery_service()

    def build_insight_options(
        self,
        *,
        report_mode: str,
    ) -> InsightOptions:
        """Build workflow insight options from the current app config."""

        analysis_config = self.insight_stage_config
        enabled = bool(analysis_config.get("ENABLED", False))
        configured_strategy = str(analysis_config.get("STRATEGY", "ai" if enabled else "noop") or ("ai" if enabled else "noop")).strip()
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
            enabled=self.notification_enabled if enabled is None else enabled,
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
        """Run the native insight stage and return only the native insight result."""

        options = self.build_insight_options(report_mode=report_mode)
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
                date_str = self.format_date()
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
                strategy=self.filter_method if strategy is None else strategy,
                frequency_file=frequency_file,
                interests_file=interests_file,
                selection_service=selection_service,
            )

        runner = insight_service or self.create_insight_service()
        insight = runner.run(snapshot, selection, options)

        if self._is_successful_insight_result(insight) and schedule is not None and schedule.once_analyze and schedule.period_key:
            self.get_storage_manager().record_period_execution(self.format_date(), schedule.period_key, "analyze")

        return insight

    def assemble_report_package(
        self,
        snapshot: HotlistSnapshot,
        selection: SelectionResult,
        insight: InsightResult,
        *,
        report_assembler: Optional[ReportPackageAssembler] = None,
    ) -> ReportPackage:
        """Assemble the Stage 6 report package from native stage outputs."""

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
        """Run the native render stage for the assembled report package."""

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
        if self.generic_webhook_url:
            channels.append("generic_webhook")
        return channels

    def cleanup(self):
        if self._storage_manager:
            self._storage_manager.cleanup_old_data()
            self._storage_manager.cleanup()
            self._storage_manager = None
