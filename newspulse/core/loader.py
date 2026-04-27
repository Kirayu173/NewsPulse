# coding=utf-8
"""Configuration loading utilities."""

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from .config import parse_multi_account_config
from .config_paths import get_config_layout, resolve_prompt_path, resolve_timeline_path
from .runtime_config import normalize_runtime_config
from newspulse.workflow.shared.ai_runtime.provider_env import resolve_chat_env_defaults
from newspulse.utils.logging import build_log_message, configure_logging, get_logger
from newspulse.utils.time import DEFAULT_TIMEZONE


DEFAULT_REGION_ORDER = ["hotlist", "new_items", "standalone", "insight"]
_MISSING = object()
logger = get_logger(__name__)


def _load_dotenv_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        normalized_key = key.strip()
        normalized_value = value.strip().strip('"').strip("'")
        os.environ.setdefault(normalized_key, normalized_value)


def _get_section(mapping: Dict[str, Any], *keys: str) -> Dict[str, Any]:
    current: Any = mapping
    for key in keys:
        if not isinstance(current, dict):
            return {}
        current = current.get(key, {})
    return current if isinstance(current, dict) else {}


def _get_present_value(mapping: Dict[str, Any], key: str):
    if isinstance(mapping, dict) and key in mapping:
        return mapping[key]
    return _MISSING


def _coalesce(*values: Any, default: Any = None) -> Any:
    for value in values:
        if value is not _MISSING and value is not None:
            return value
    return default


def _get_env_bool(key: str) -> Optional[bool]:
    value = os.environ.get(key, "").strip().lower()
    if not value:
        return None
    return value in ("true", "1")


def _get_env_int(key: str, default: int = 0) -> int:
    value = os.environ.get(key, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_env_int_or_none(key: str) -> Optional[int]:
    value = os.environ.get(key, "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _get_env_float_or_none(key: str) -> Optional[float]:
    value = os.environ.get(key, "").strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _get_env_str(key: str, default: str = "") -> str:
    return os.environ.get(key, "").strip() or default


def _get_env_first(*keys: str, default: str = "") -> str:
    for key in keys:
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return default


def _load_app_config(config_data: Dict[str, Any]) -> Dict[str, Any]:
    app_config = config_data.get("app", {})
    advanced = config_data.get("advanced", {})
    debug_env = _get_env_bool("DEBUG")
    return {
        "VERSION_CHECK_URL": advanced.get("version_check_url", ""),
        "CONFIGS_VERSION_CHECK_URL": advanced.get("configs_version_check_url", ""),
        "SHOW_VERSION_UPDATE": app_config.get("show_version_update", True),
        "TIMEZONE": _get_env_str("TIMEZONE") or app_config.get("timezone", DEFAULT_TIMEZONE),
        "DEBUG": advanced.get("debug", False) if debug_env is None else debug_env,
    }


def _load_crawler_config(config_data: Dict[str, Any]) -> Dict[str, Any]:
    advanced = config_data.get("advanced", {})
    crawler = advanced.get("crawler", {})
    platforms = config_data.get("platforms", {})
    return {
        "REQUEST_INTERVAL": crawler.get("request_interval", 100),
        "USE_PROXY": crawler.get("use_proxy", False),
        "DEFAULT_PROXY": crawler.get("default_proxy", ""),
        "ENABLE_CRAWLER": platforms.get("enabled", True),
    }


def _load_report_config(config_data: Dict[str, Any]) -> Dict[str, Any]:
    report = config_data.get("report", {})
    sort_by_position_env = _get_env_bool("SORT_BY_POSITION_FIRST")
    max_news_env = _get_env_int_or_none("MAX_NEWS_PER_KEYWORD")
    return {
        "REPORT_MODE": report.get("mode", "daily"),
        "DISPLAY_MODE": report.get("display_mode", "keyword"),
        "RANK_THRESHOLD": report.get("rank_threshold", 10),
        "SORT_BY_POSITION_FIRST": report.get("sort_by_position_first", False) if sort_by_position_env is None else sort_by_position_env,
        "MAX_NEWS_PER_KEYWORD": report.get("max_news_per_keyword", 0) if max_news_env is None else max_news_env,
    }


def _load_notification_config(config_data: Dict[str, Any]) -> Dict[str, Any]:
    notification = config_data.get("notification", {})
    advanced = config_data.get("advanced", {})
    batch_size = advanced.get("batch_size", {})
    return {
        "ENABLE_NOTIFICATION": notification.get("enabled", True),
        "MESSAGE_BATCH_SIZE": batch_size.get("default", 4000),
        "BATCH_SEND_INTERVAL": advanced.get("batch_send_interval", 1.0),
        "MAX_ACCOUNTS_PER_CHANNEL": _get_env_int("MAX_ACCOUNTS_PER_CHANNEL") or advanced.get("max_accounts_per_channel", 3),
    }


def _load_logging_config(config_data: Dict[str, Any]) -> Dict[str, Any]:
    advanced = config_data.get("advanced", {})
    json_env = _get_env_bool("LOG_JSON")
    return {
        "LOG_LEVEL": _get_env_str("LOG_LEVEL") or advanced.get("log_level", "INFO"),
        "LOG_FILE": _get_env_str("LOG_FILE") or advanced.get("log_file", ""),
        "LOG_JSON": advanced.get("log_json", False) if json_env is None else json_env,
    }


def _load_schedule_config(config_data: Dict[str, Any]) -> Dict[str, Any]:
    schedule = config_data.get("schedule", {})
    enabled_env = _get_env_bool("SCHEDULE_ENABLED")
    preset_env = _get_env_str("SCHEDULE_PRESET")
    return {
        "enabled": schedule.get("enabled", False) if enabled_env is None else enabled_env,
        "preset": preset_env or schedule.get("preset", "always_on"),
    }


def _load_timeline_data(config_root: Path) -> Dict[str, Any]:
    timeline_path = resolve_timeline_path(config_root=config_root)
    if not timeline_path.exists():
        logger.warning("%s", build_log_message("config.timeline_missing", path=timeline_path))
        return {
            "presets": {},
            "custom": {
                "default": {
                    "collect": True,
                    "analyze": False,
                    "push": False,
                    "report_mode": "current",
                    "ai_mode": "follow_report",
                    "once": {"analyze": False, "push": False},
                },
                "periods": {},
                "day_plans": {"all_day": {"periods": []}},
                "week_map": {i: "all_day" for i in range(1, 8)},
            },
        }

    with open(timeline_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    logger.info("%s", build_log_message("config.timeline_loaded", path=timeline_path))
    return data or {}


def _load_weight_config(config_data: Dict[str, Any]) -> Dict[str, Any]:
    advanced = config_data.get("advanced", {})
    weight = advanced.get("weight", {})
    return {
        "RANK_WEIGHT": weight.get("rank", 0.6),
        "FREQUENCY_WEIGHT": weight.get("frequency", 0.3),
        "HOTNESS_WEIGHT": weight.get("hotness", 0.1),
    }


def _load_display_config(config_data: Dict[str, Any]) -> Dict[str, Any]:
    display = config_data.get("display", {})
    regions = display.get("regions", {})
    standalone = display.get("standalone", {})

    region_order = [region for region in display.get("region_order", DEFAULT_REGION_ORDER) if region in set(DEFAULT_REGION_ORDER)]
    if not region_order:
        region_order = list(DEFAULT_REGION_ORDER)

    return {
        "REGION_ORDER": region_order,
        "REGIONS": {
            "HOTLIST": regions.get("hotlist", True),
            "NEW_ITEMS": regions.get("new_items", True),
            "STANDALONE": regions.get("standalone", False),
            "INSIGHT": regions.get("insight", True),
        },
        "STANDALONE": {
            "PLATFORMS": standalone.get("platforms", []),
            "MAX_ITEMS": standalone.get("max_items", 20),
        },
    }


def _load_ai_config(config_data: Dict[str, Any]) -> Dict[str, Any]:
    ai = _get_section(config_data, "ai", "runtime") or config_data.get("ai", {})
    timeout_env = _get_env_int_or_none("AI_TIMEOUT")
    temperature_env = _get_env_float_or_none("AI_TEMPERATURE")
    max_tokens_env = _get_env_int_or_none("AI_MAX_TOKENS")
    num_retries_env = _get_env_int_or_none("AI_NUM_RETRIES")
    env_defaults = resolve_chat_env_defaults(
        provider_family=ai.get("provider_family", "auto"),
        api_base=ai.get("api_base", ""),
        model=ai.get("model", ""),
    )
    return {
        "MODEL": _get_env_first("AI_MODEL", "MODEL") or env_defaults.get("MODEL", "") or ai.get("model", ""),
        "API_KEY": _get_env_first("AI_API_KEY", "API_KEY") or env_defaults.get("API_KEY", "") or ai.get("api_key", ""),
        "API_BASE": _get_env_first("AI_API_BASE", "AI_BASE_URL", "API_BASE", "BASE_URL") or env_defaults.get("API_BASE", "") or ai.get("api_base", ""),
        "PROVIDER_FAMILY": _get_env_first("AI_PROVIDER_FAMILY", "PROVIDER_FAMILY") or ai.get("provider_family", "auto"),
        "TIMEOUT": ai.get("timeout", 120) if timeout_env is None else timeout_env,
        "TEMPERATURE": ai.get("temperature", 1.0) if temperature_env is None else temperature_env,
        "MAX_TOKENS": ai.get("max_tokens", 5000) if max_tokens_env is None else max_tokens_env,
        "NUM_RETRIES": ai.get("num_retries", 2) if num_retries_env is None else num_retries_env,
        "EXTRA_PARAMS": ai.get("extra_params", {}),
    }


def _merge_ai_runtime_config(base_ai_config: Dict[str, Any], section_config: Dict[str, Any], env_prefix: str) -> Dict[str, Any]:
    merged = dict(base_ai_config)

    string_fields = {
        "MODEL": "model",
        "API_KEY": "api_key",
        "API_BASE": "api_base",
        "PROVIDER_FAMILY": "provider_family",
    }
    int_fields = {"TIMEOUT": "timeout", "MAX_TOKENS": "max_tokens", "NUM_RETRIES": "num_retries"}

    for target_key, yaml_key in string_fields.items():
        env_value = _get_env_str(f"{env_prefix}_{target_key}")
        if not env_value and target_key == "API_BASE":
            env_value = _get_env_str(f"{env_prefix}_BASE_URL")
        if env_value:
            merged[target_key] = env_value
        elif section_config.get(yaml_key) not in (None, ""):
            merged[target_key] = section_config.get(yaml_key)

    for target_key, yaml_key in int_fields.items():
        env_value = _get_env_int_or_none(f"{env_prefix}_{target_key}")
        if env_value is not None:
            merged[target_key] = env_value
        elif section_config.get(yaml_key) is not None:
            merged[target_key] = section_config.get(yaml_key)

    temperature_env = _get_env_float_or_none(f"{env_prefix}_TEMPERATURE")
    if temperature_env is not None:
        merged["TEMPERATURE"] = temperature_env
    elif section_config.get("temperature") is not None:
        merged["TEMPERATURE"] = section_config.get("temperature")

    if section_config.get("extra_params") is not None:
        merged["EXTRA_PARAMS"] = section_config.get("extra_params")

    return merged


def _get_ai_operation_config(config_data: Dict[str, Any], operation_key: str) -> Dict[str, Any]:
    return _get_section(config_data, "ai", "operations", operation_key)


def _load_workflow_selection_config(config_data: Dict[str, Any]) -> Dict[str, Any]:
    selection = _get_section(config_data, "workflow", "selection")
    selection_ai = _get_section(selection, "ai")
    selection_semantic = _get_section(selection, "semantic")

    env_ai_filter = _get_env_bool("AI_FILTER_ENABLED")
    strategy = str(
        _coalesce(
            _get_present_value(selection, "strategy"),
            default="keyword",
        )
        or "keyword"
    ).strip() or "keyword"
    if env_ai_filter is True:
        strategy = "ai"

    return {
        "STRATEGY": strategy,
        "FREQUENCY_FILE": _coalesce(
            _get_present_value(selection, "frequency_file"),
            default=None,
        ),
        "PRIORITY_SORT_ENABLED": bool(
            _coalesce(
                _get_present_value(selection, "priority_sort_enabled"),
                default=False,
            )
        ),
        "AI": {
            "INTERESTS_FILE": _coalesce(
                _get_present_value(selection_ai, "interests_file"),
                default=None,
            ),
            "BATCH_SIZE": int(
                _coalesce(
                    _get_present_value(selection_ai, "batch_size"),
                    default=200,
                )
            ),
            "BATCH_INTERVAL": float(
                _coalesce(
                    _get_present_value(selection_ai, "batch_interval"),
                    default=5,
                )
            ),
            "CONCURRENCY": int(
                _coalesce(
                    _get_present_value(selection_ai, "concurrency"),
                    default=3,
                )
                or 3
            ),
            "MIN_SCORE": float(
                _coalesce(
                    _get_present_value(selection_ai, "min_score"),
                    default=0,
                )
                or 0
            ),
            "RECLASSIFY_THRESHOLD": float(
                _coalesce(
                    _get_present_value(selection_ai, "reclassify_threshold"),
                    default=0.6,
                )
            ),
            "FALLBACK_TO_KEYWORD": bool(
                _coalesce(
                    _get_present_value(selection_ai, "fallback_to_keyword"),
                    default=True,
                )
            ),
        },
        "SEMANTIC": {
            "ENABLED": bool(
                _coalesce(
                    _get_present_value(selection_semantic, "enabled"),
                    default=True,
                )
            ),
            "TOP_K": int(
                _coalesce(
                    _get_present_value(selection_semantic, "top_k"),
                    default=3,
                )
            ),
            "MIN_SCORE": float(
                _coalesce(
                    _get_present_value(selection_semantic, "min_score"),
                    default=0.55,
                )
                or 0.55
            ),
            "DIRECT_THRESHOLD": float(
                _coalesce(
                    _get_present_value(selection_semantic, "direct_threshold"),
                    default=0.78,
                )
                or 0.78
            ),
        },
    }


def _coerce_string_list(value: Any, default: list[str]) -> list[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        return list(default)
    normalized = [str(item or "").strip() for item in values if str(item or "").strip()]
    return normalized or list(default)


def _load_workflow_insight_config(config_data: Dict[str, Any], config_root: Path) -> Dict[str, Any]:
    insight = _get_section(config_data, "workflow", "insight")
    content = _get_section(insight, "content")
    summary = _get_section(insight, "summary")
    enabled_env = _get_env_bool("AI_ANALYSIS_ENABLED")
    enabled = bool(
        _coalesce(
            _get_present_value(insight, "enabled"),
            default=False,
        )
        if enabled_env is None
        else enabled_env
    )

    return {
        "ENABLED": enabled,
        "STRATEGY": str(
            _coalesce(
                _get_present_value(insight, "strategy"),
                default="ai" if enabled else "noop",
            )
            or ("ai" if enabled else "noop")
        ).strip()
        or ("ai" if enabled else "noop"),
        "LANGUAGE": str(
            _coalesce(
                _get_present_value(insight, "language"),
                default="Chinese",
            )
            or "Chinese"
        ),
        "MODE": str(
            _coalesce(
                _get_present_value(insight, "mode"),
                default="follow_report",
            )
            or "follow_report"
        ),
        "MAX_ITEMS": int(
            _coalesce(
                _get_present_value(insight, "max_items"),
                default=50,
            )
        ),
        "CONTENT": {
            "ENABLED": bool(_coalesce(_get_present_value(content, "enabled"), default=False)),
            "FETCH_TIMEOUT_SECONDS": int(
                _coalesce(_get_present_value(content, "fetch_timeout_seconds"), default=8) or 8
            ),
            "FETCH_CONCURRENCY": int(_coalesce(_get_present_value(content, "fetch_concurrency"), default=3) or 3),
            "MAX_RAW_CHARS": int(_coalesce(_get_present_value(content, "max_raw_chars"), default=120000) or 120000),
            "MAX_REDUCED_CHARS": int(_coalesce(_get_present_value(content, "max_reduced_chars"), default=6000) or 6000),
            "EXTRACTOR_ORDER": _coerce_string_list(
                _coalesce(_get_present_value(content, "extractor_order"), default=[]),
                ["trafilatura", "readability", "beautifulsoup"],
            ),
        },
        "SUMMARY": {
            "ITEM_PROMPT_FILE": str(
                resolve_prompt_path(
                    str(_coalesce(_get_present_value(summary, "item_prompt_file"), default="insight/item_summary_prompt.txt")),
                    config_root=config_root,
                )
            ),
            "REPORT_PROMPT_FILE": str(
                resolve_prompt_path(
                    str(_coalesce(_get_present_value(summary, "report_prompt_file"), default="insight/report_summary_prompt.txt")),
                    config_root=config_root,
                )
            ),
            "ITEM_CONCURRENCY": int(_coalesce(_get_present_value(summary, "item_concurrency"), default=3) or 3),
            "ITEM_SUMMARY_MAX_CHARS": int(
                _coalesce(_get_present_value(summary, "item_summary_max_chars"), default=220) or 220
            ),
            "REPORT_SUMMARY_MAX_CHARS": int(
                _coalesce(_get_present_value(summary, "report_summary_max_chars"), default=300) or 300
            ),
        },
    }

def _load_workflow_config(config_data: Dict[str, Any], config_root: Path) -> Dict[str, Any]:
    return {
        "SELECTION": _load_workflow_selection_config(config_data),
        "INSIGHT": _load_workflow_insight_config(config_data, config_root),
    }


def _load_ai_selection_operation_config(config_data: Dict[str, Any], config_root: Path) -> Dict[str, Any]:
    operation = _get_ai_operation_config(config_data, "selection")
    return {
        "PROMPT_FILE": str(
            resolve_prompt_path(
                str(_coalesce(_get_present_value(operation, "prompt_file"), default="prompt.txt")),
                config_root=config_root,
                config_subdir="ai_filter",
            )
        ),
        "EXTRACT_PROMPT_FILE": str(
            resolve_prompt_path(
                str(_coalesce(_get_present_value(operation, "extract_prompt_file"), default="extract_prompt.txt")),
                config_root=config_root,
                config_subdir="ai_filter",
            )
        ),
        "UPDATE_TAGS_PROMPT_FILE": str(
            resolve_prompt_path(
                str(_coalesce(_get_present_value(operation, "update_tags_prompt_file"), default="update_tags_prompt.txt")),
                config_root=config_root,
                config_subdir="ai_filter",
            )
        ),
        "TIMEOUT": _coalesce(_get_present_value(operation, "timeout"), default=None),
        "NUM_RETRIES": _coalesce(_get_present_value(operation, "num_retries"), default=None),
        "EXTRA_PARAMS": _coalesce(_get_present_value(operation, "extra_params"), default={}),
        "RUNTIME_CACHE": _load_ai_runtime_cache_config(operation),
    }


def _load_ai_analysis_model_config(config_data: Dict[str, Any], base_ai_config: Dict[str, Any]) -> Dict[str, Any]:
    return _merge_ai_runtime_config(base_ai_config, _get_ai_operation_config(config_data, "insight"), "AI_ANALYSIS")


def _load_ai_filter_model_config(config_data: Dict[str, Any], base_ai_config: Dict[str, Any]) -> Dict[str, Any]:
    return _merge_ai_runtime_config(base_ai_config, _get_ai_operation_config(config_data, "selection"), "AI_FILTER")


def _load_ai_insight_operation_config(config_data: Dict[str, Any], config_root: Path) -> Dict[str, Any]:
    operation = _get_ai_operation_config(config_data, "insight")
    return {
        "PROMPT_FILE": str(
            resolve_prompt_path(
                str(_coalesce(_get_present_value(operation, "prompt_file"), default="global_insight_prompt.txt")),
                config_root=config_root,
            )
        ),
        "ITEM_PROMPT_FILE": str(
            resolve_prompt_path(
                str(_coalesce(_get_present_value(operation, "item_prompt_file"), default="insight/item_summary_prompt.txt")),
                config_root=config_root,
            )
        ),
        "REPORT_PROMPT_FILE": str(
            resolve_prompt_path(
                str(_coalesce(_get_present_value(operation, "report_prompt_file"), default="insight/report_summary_prompt.txt")),
                config_root=config_root,
            )
        ),
        "TIMEOUT": _coalesce(_get_present_value(operation, "timeout"), default=None),
        "NUM_RETRIES": _coalesce(_get_present_value(operation, "num_retries"), default=None),
        "EXTRA_PARAMS": dict(_coalesce(_get_present_value(operation, "extra_params"), default={}) or {}),
        "RUNTIME_CACHE": _load_ai_runtime_cache_config(operation),
    }

def _load_ai_analysis_config(workflow_config: Dict[str, Any], operation_config: Dict[str, Any]) -> Dict[str, Any]:
    insight = workflow_config["INSIGHT"]
    summary = dict(insight.get("SUMMARY", {}) or {})
    summary.setdefault("ITEM_PROMPT_FILE", operation_config["ITEM_PROMPT_FILE"])
    summary.setdefault("REPORT_PROMPT_FILE", operation_config["REPORT_PROMPT_FILE"])
    return {
        "ENABLED": insight["ENABLED"],
        "STRATEGY": insight["STRATEGY"],
        "LANGUAGE": insight["LANGUAGE"],
        "PROMPT_FILE": operation_config["PROMPT_FILE"],
        "TIMEOUT": operation_config.get("TIMEOUT"),
        "NUM_RETRIES": operation_config.get("NUM_RETRIES"),
        "EXTRA_PARAMS": operation_config.get("EXTRA_PARAMS", {}),
        "RUNTIME_CACHE": dict(operation_config.get("RUNTIME_CACHE", {}) or {}),
        "CONTENT": dict(insight.get("CONTENT", {}) or {}),
        "SUMMARY": summary,
        "MODE": insight["MODE"],
        "MAX_ITEMS": insight["MAX_ITEMS"],
    }

def _load_ai_filter_config(workflow_config: Dict[str, Any], operation_config: Dict[str, Any]) -> Dict[str, Any]:
    selection_ai = workflow_config["SELECTION"]["AI"]
    return {
        "BATCH_SIZE": selection_ai["BATCH_SIZE"],
        "BATCH_INTERVAL": selection_ai["BATCH_INTERVAL"],
        "CONCURRENCY": selection_ai["CONCURRENCY"],
        "TIMEOUT": operation_config.get("TIMEOUT"),
        "NUM_RETRIES": operation_config.get("NUM_RETRIES"),
        "EXTRA_PARAMS": operation_config.get("EXTRA_PARAMS", {}),
        "RUNTIME_CACHE": dict(operation_config.get("RUNTIME_CACHE", {}) or {}),
        "INTERESTS_FILE": selection_ai["INTERESTS_FILE"],
        "PROMPT_FILE": operation_config["PROMPT_FILE"],
        "EXTRACT_PROMPT_FILE": operation_config["EXTRACT_PROMPT_FILE"],
        "UPDATE_TAGS_PROMPT_FILE": operation_config["UPDATE_TAGS_PROMPT_FILE"],
        "RECLASSIFY_THRESHOLD": selection_ai["RECLASSIFY_THRESHOLD"],
        "MIN_SCORE": selection_ai["MIN_SCORE"],
        "FALLBACK_TO_KEYWORD": selection_ai["FALLBACK_TO_KEYWORD"],
    }


def _load_ai_runtime_cache_config(operation_config: Dict[str, Any]) -> Dict[str, Any]:
    runtime_cache = _get_section(operation_config, "runtime_cache")
    if not runtime_cache:
        runtime_cache = _get_section(operation_config, "llm_cache")
    if not runtime_cache:
        return {}

    return {
        "ENABLED": bool(
            _coalesce(
                _get_present_value(runtime_cache, "enabled"),
                default=True,
            )
        ),
        "TTL_SECONDS": int(
            _coalesce(
                _get_present_value(runtime_cache, "ttl_seconds"),
                default=3600,
            )
        ),
        "MAX_ENTRIES": int(
            _coalesce(
                _get_present_value(runtime_cache, "max_entries"),
                default=512,
            )
        ),
    }


def _load_filter_config(workflow_config: Dict[str, Any]) -> Dict[str, Any]:
    selection = workflow_config["SELECTION"]
    return {
        "METHOD": selection["STRATEGY"],
        "FREQUENCY_FILE": selection.get("FREQUENCY_FILE"),
        "PRIORITY_SORT_ENABLED": selection["PRIORITY_SORT_ENABLED"],
    }


def _load_storage_config(config_data: Dict[str, Any]) -> Dict[str, Any]:
    storage = config_data.get("storage", {})
    formats = storage.get("formats", {})
    local = storage.get("local", {})
    txt_enabled_env = _get_env_bool("STORAGE_TXT_ENABLED")
    html_enabled_env = _get_env_bool("STORAGE_HTML_ENABLED")
    retention_days_env = _get_env_int_or_none("STORAGE_RETENTION_DAYS")
    if retention_days_env is None:
        retention_days_env = _get_env_int_or_none("LOCAL_RETENTION_DAYS")
    return {
        "BACKEND": "local",
        "FORMATS": {
            "SQLITE": formats.get("sqlite", True),
            "TXT": formats.get("txt", True) if txt_enabled_env is None else txt_enabled_env,
            "HTML": formats.get("html", True) if html_enabled_env is None else html_enabled_env,
        },
        "LOCAL": {
            "DATA_DIR": local.get("data_dir", "output"),
            "RETENTION_DAYS": local.get("retention_days", 0) if retention_days_env is None else retention_days_env,
        },
    }


def _load_webhook_config(config_data: Dict[str, Any]) -> Dict[str, Any]:
    notification = config_data.get("notification", {})
    channels = notification.get("channels", {})
    generic = channels.get("generic_webhook", {})
    return {
        "GENERIC_WEBHOOK_URL": _get_env_str("GENERIC_WEBHOOK_URL") or generic.get("webhook_url", ""),
        "GENERIC_WEBHOOK_TEMPLATE": _get_env_str("GENERIC_WEBHOOK_TEMPLATE") or generic.get("payload_template", ""),
    }


def _print_notification_sources(config: Dict[str, Any]) -> None:
    notification_sources = []
    max_accounts = config["MAX_ACCOUNTS_PER_CHANNEL"]

    if config.get("GENERIC_WEBHOOK_URL"):
        accounts = parse_multi_account_config(config["GENERIC_WEBHOOK_URL"])
        count = min(len(accounts), max_accounts)
        source = "环境变量" if os.environ.get("GENERIC_WEBHOOK_URL") else "配置文件"
        notification_sources.append(f"通用 Webhook({source}, {count} 个账号)")

    if notification_sources:
        logger.info(
            "%s",
            build_log_message(
                "config.notifications_enabled",
                channels=notification_sources,
                max_accounts=max_accounts,
            ),
        )
    else:
        logger.info("%s", build_log_message("config.notifications_missing"))


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    layout = get_config_layout(config_path)
    resolved_config_path = layout.config_path
    dotenv_root = layout.config_root.parent
    _load_dotenv_file(dotenv_root / ".env")
    if config_path is None:
        _load_dotenv_file(layout.project_root / ".env")

    if not resolved_config_path.exists():
        raise FileNotFoundError(f"config file not found: {resolved_config_path}")

    with open(resolved_config_path, "r", encoding="utf-8") as f:
        config_data = yaml.safe_load(f) or {}

    config: Dict[str, Any] = {}
    config.update(_load_app_config(config_data))
    config.update(_load_logging_config(config_data))
    configure_logging(config["LOG_LEVEL"], config["LOG_FILE"], config["LOG_JSON"])
    logger.info("%s", build_log_message("config.loaded", path=resolved_config_path))
    config.update(_load_crawler_config(config_data))
    config.update(_load_report_config(config_data))
    config.update(_load_notification_config(config_data))

    config["SCHEDULE"] = _load_schedule_config(config_data)
    config["_TIMELINE_DATA"] = _load_timeline_data(layout.config_root)
    config["WEIGHT_CONFIG"] = _load_weight_config(config_data)
    config["PLATFORMS"] = config_data.get("platforms", {}).get("sources", [])

    workflow_config = _load_workflow_config(config_data, layout.config_root)
    selection_operation_config = _load_ai_selection_operation_config(config_data, layout.config_root)
    insight_operation_config = _load_ai_insight_operation_config(config_data, layout.config_root)

    config["WORKFLOW"] = workflow_config
    config["AI"] = _load_ai_config(config_data)
    config["AI_ANALYSIS"] = _load_ai_analysis_config(workflow_config, insight_operation_config)
    config["AI_ANALYSIS_MODEL"] = _load_ai_analysis_model_config(config_data, config["AI"])
    config["AI_FILTER"] = _load_ai_filter_config(workflow_config, selection_operation_config)
    config["AI_FILTER_MODEL"] = _load_ai_filter_model_config(config_data, config["AI"])

    config["FILTER"] = _load_filter_config(workflow_config)
    config["DISPLAY"] = _load_display_config(config_data)
    config["STORAGE"] = _load_storage_config(config_data)
    config.update(_load_webhook_config(config_data))
    config["_PATHS"] = {
        "PROJECT_ROOT": str(layout.project_root),
        "CONFIG_ROOT": str(layout.config_root),
        "CONFIG_PATH": str(layout.config_path),
    }

    config = normalize_runtime_config(config)
    _print_notification_sources(config)
    return config
