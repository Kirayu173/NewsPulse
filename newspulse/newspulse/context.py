# coding=utf-8
"""Application context helpers."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from newspulse.core.scheduler import ResolvedSchedule
from newspulse.core import (
    Scheduler,
    detect_latest_new_titles,
    read_all_today_titles,
)
from newspulse.storage import get_storage_manager
from newspulse.workflow.delivery import DeliveryService, GenericWebhookDeliveryAdapter
from newspulse.workflow.insight import InsightService
from newspulse.workflow.localization import LocalizationService
from newspulse.workflow.render import HTMLRenderAdapter, HotlistReportAssembler, NotificationRenderAdapter, RenderService
from newspulse.utils.time import (
    DEFAULT_TIMEZONE,
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
    def workflow_config(self) -> Dict[str, Any]:
        workflow = self.config.get("WORKFLOW", {})
        if isinstance(workflow, dict) and workflow:
            return workflow
        workflow = self.config.get("workflow", {})
        return workflow if isinstance(workflow, dict) else {}

    @property
    def raw_ai_config(self) -> Dict[str, Any]:
        ai = self.config.get("ai", {})
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
    def display_mode(self) -> str:
        return self.config.get("DISPLAY_MODE", "keyword")

    @property
    def show_new_section(self) -> bool:
        return self.config.get("DISPLAY", {}).get("REGIONS", {}).get("NEW_ITEMS", True)

    @property
    def region_order(self) -> List[str]:
        return self.config.get(
            "DISPLAY", {}
        ).get("REGION_ORDER", ["hotlist", "new_items", "standalone", "insight"])

    @property
    def filter_method(self) -> str:
        return str(self.selection_stage_config.get("STRATEGY", "keyword") or "keyword")

    @property
    def ai_priority_sort_enabled(self) -> bool:
        return bool(self.selection_stage_config.get("PRIORITY_SORT_ENABLED", False))

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
        return {
            "ENABLED": bool(insight.get("ENABLED", False)),
            "STRATEGY": str(insight.get("STRATEGY", "noop") or "noop"),
            "LANGUAGE": str(insight.get("LANGUAGE", "Chinese") or "Chinese"),
            "PROMPT_FILE": str(
                self._mapping_get(operation, "PROMPT_FILE", "prompt_file", default="ai_analysis_prompt.txt")
                or "ai_analysis_prompt.txt"
            ),
            "MODE": str(insight.get("MODE", "follow_report") or "follow_report"),
            "MAX_NEWS_FOR_ANALYSIS": int(insight.get("MAX_ITEMS", 50) or 50),
            "INCLUDE_RANK_TIMELINE": bool(insight.get("INCLUDE_RANK_TIMELINE", False)),
            "INCLUDE_STANDALONE": bool(insight.get("INCLUDE_STANDALONE", False)),
        }

    @property
    def ai_translation_config(self) -> Dict[str, Any]:
        localization = self.localization_stage_config
        scope = localization.get("SCOPE", {})
        operation = self._get_ai_operation_mapping("localization", legacy_key="AI_TRANSLATION")
        return {
            "ENABLED": bool(localization.get("ENABLED", False)),
            "STRATEGY": str(localization.get("STRATEGY", "noop") or "noop"),
            "LANGUAGE": str(localization.get("LANGUAGE", "English") or "English"),
            "PROMPT_FILE": str(
                self._mapping_get(operation, "PROMPT_FILE", "prompt_file", default="ai_translation_prompt.txt")
                or "ai_translation_prompt.txt"
            ),
            "TIMEOUT": self._mapping_get(operation, "TIMEOUT", "timeout"),
            "NUM_RETRIES": self._mapping_get(operation, "NUM_RETRIES", "num_retries"),
            "EXTRA_PARAMS": self._coerce_mapping(
                self._mapping_get(operation, "EXTRA_PARAMS", "extra_params", default={}),
            ),
            "SCOPE": {
                "HOTLIST": bool(scope.get("SELECTION_TITLES", True)),
                "NEW_ITEMS": bool(scope.get("NEW_ITEMS", True)),
                "STANDALONE": bool(scope.get("STANDALONE", True)),
                "INSIGHT": bool(scope.get("INSIGHT_SECTIONS", False)),
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
    def ai_translation_model_config(self) -> Dict[str, Any]:
        configured = self.config.get("AI_TRANSLATION_MODEL", {})
        if isinstance(configured, dict) and configured:
            return configured
        return self._merge_ai_runtime_config(
            self.ai_runtime_config,
            self._get_ai_operation_mapping("localization", legacy_key="AI_TRANSLATION"),
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
        }

    @property
    def insight_stage_config(self) -> Dict[str, Any]:
        workflow_insight = self._get_workflow_stage("INSIGHT", "insight")
        if workflow_insight:
            enabled = bool(self._mapping_get(workflow_insight, "ENABLED", "enabled", default=False))
            return {
                "ENABLED": enabled,
                "STRATEGY": str(
                    self._mapping_get(workflow_insight, "STRATEGY", "strategy", default="ai" if enabled else "noop")
                    or ("ai" if enabled else "noop")
                ),
                "MODE": str(self._mapping_get(workflow_insight, "MODE", "mode", default="follow_report") or "follow_report"),
                "MAX_ITEMS": int(self._mapping_get(workflow_insight, "MAX_ITEMS", "max_items", default=50) or 50),
                "INCLUDE_STANDALONE": bool(
                    self._mapping_get(workflow_insight, "INCLUDE_STANDALONE", "include_standalone", default=False)
                ),
                "INCLUDE_RANK_TIMELINE": bool(
                    self._mapping_get(workflow_insight, "INCLUDE_RANK_TIMELINE", "include_rank_timeline", default=False)
                ),
                "LANGUAGE": str(self._mapping_get(workflow_insight, "LANGUAGE", "language", default="Chinese") or "Chinese"),
            }

        analysis_config = self.config.get("AI_ANALYSIS", {})
        enabled = bool(analysis_config.get("ENABLED", False))
        return {
            "ENABLED": enabled,
            "STRATEGY": str(analysis_config.get("STRATEGY", "ai" if enabled else "noop") or ("ai" if enabled else "noop")),
            "MODE": str(analysis_config.get("MODE", "follow_report") or "follow_report"),
            "MAX_ITEMS": int(analysis_config.get("MAX_NEWS_FOR_ANALYSIS", 50) or 50),
            "INCLUDE_STANDALONE": bool(analysis_config.get("INCLUDE_STANDALONE", False)),
            "INCLUDE_RANK_TIMELINE": bool(analysis_config.get("INCLUDE_RANK_TIMELINE", False)),
            "LANGUAGE": str(analysis_config.get("LANGUAGE", "Chinese") or "Chinese"),
        }

    @property
    def localization_stage_config(self) -> Dict[str, Any]:
        workflow_localization = self._get_workflow_stage("LOCALIZATION", "localization")
        if workflow_localization:
            workflow_scope = self._get_nested_mapping(workflow_localization, "SCOPE", "scope")
            enabled = bool(self._mapping_get(workflow_localization, "ENABLED", "enabled", default=False))
            return {
                "ENABLED": enabled,
                "STRATEGY": str(
                    self._mapping_get(workflow_localization, "STRATEGY", "strategy", default="ai" if enabled else "noop")
                    or ("ai" if enabled else "noop")
                ),
                "LANGUAGE": str(
                    self._mapping_get(workflow_localization, "LANGUAGE", "language", default="English") or "English"
                ),
                "SCOPE": {
                    "SELECTION_TITLES": bool(
                        self._mapping_get(workflow_scope, "SELECTION_TITLES", "selection_titles", default=True)
                    ),
                    "NEW_ITEMS": bool(self._mapping_get(workflow_scope, "NEW_ITEMS", "new_items", default=True)),
                    "STANDALONE": bool(self._mapping_get(workflow_scope, "STANDALONE", "standalone", default=True)),
                    "INSIGHT_SECTIONS": bool(
                        self._mapping_get(workflow_scope, "INSIGHT_SECTIONS", "insight_sections", default=False)
                    ),
                },
            }

        translation_config = self.config.get("AI_TRANSLATION", {})
        scope = translation_config.get("SCOPE", {})
        hotlist_scope = bool(scope.get("HOTLIST", True))
        return {
            "ENABLED": bool(translation_config.get("ENABLED", False)),
            "STRATEGY": str(
                translation_config.get("STRATEGY", "ai" if translation_config.get("ENABLED", False) else "noop")
                or ("ai" if translation_config.get("ENABLED", False) else "noop")
            ),
            "LANGUAGE": str(translation_config.get("LANGUAGE", "English") or "English"),
            "SCOPE": {
                "SELECTION_TITLES": hotlist_scope,
                "NEW_ITEMS": bool(scope.get("NEW_ITEMS", hotlist_scope)),
                "STANDALONE": bool(scope.get("STANDALONE", True)),
                "INSIGHT_SECTIONS": bool(scope.get("INSIGHT", False)),
            },
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

        selection_config = self.selection_stage_config
        selection_ai = selection_config.get("AI", {})
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
            ai_analysis_config=self.ai_analysis_config,
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
            ai_translation_config=self.ai_translation_config,
            ai_runtime_config=self.ai_translation_model_config,
            config_root=str(self.config_root),
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

        analysis_config = self.insight_stage_config
        enabled = bool(analysis_config.get("ENABLED", False))
        configured_strategy = str(analysis_config.get("STRATEGY", "ai" if enabled else "noop") or ("ai" if enabled else "noop")).strip()
        requested_mode = str(analysis_config.get("MODE", "follow_report") or "follow_report").strip()
        effective_mode = requested_mode if requested_mode in {"daily", "current", "incremental"} else report_mode

        return InsightOptions(
            enabled=enabled,
            strategy=configured_strategy or ("ai" if enabled else "noop"),
            mode=effective_mode,
            max_items=int(analysis_config.get("MAX_ITEMS", 50) or 50),
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

        translation_config = self.localization_stage_config
        enabled = bool(translation_config.get("ENABLED", False))
        scope = translation_config.get("SCOPE", {})
        hotlist_scope = bool(scope.get("SELECTION_TITLES", True))
        new_items_scope = bool(scope.get("NEW_ITEMS", hotlist_scope))

        return LocalizationOptions(
            enabled=enabled,
            strategy=strategy or str(translation_config.get("STRATEGY", "ai" if enabled else "noop") or ("ai" if enabled else "noop")),
            language=str(translation_config.get("LANGUAGE", "English")),
            scope=LocalizationScope(
                selection_titles=hotlist_scope,
                new_items=new_items_scope,
                standalone=bool(scope.get("STANDALONE", True)),
                insight_sections=bool(scope.get("INSIGHT_SECTIONS", False)),
            ),
            metadata={
                "workflow_scope": dict(scope),
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

        if self._is_successful_insight_result(insight) and schedule is not None and schedule.once_analyze and schedule.period_key:
            self.get_storage_manager().record_period_execution(self.format_date(), schedule.period_key, "analyze")

        return insight

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

    def cleanup(self):
        if self._storage_manager:
            self._storage_manager.cleanup_old_data()
            self._storage_manager.cleanup()
            self._storage_manager = None
