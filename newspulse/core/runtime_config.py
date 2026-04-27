# coding=utf-8
"""Shared runtime configuration normalization helpers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict


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


def mapping_get(mapping: Dict[str, Any], *names: str, default: Any = None) -> Any:
    if not isinstance(mapping, dict):
        return default
    for name in names:
        if name in mapping and mapping[name] is not None:
            return mapping[name]
    return default


def get_nested_mapping(mapping: Dict[str, Any], *names: str) -> Dict[str, Any]:
    if not isinstance(mapping, dict):
        return {}
    for name in names:
        value = mapping.get(name)
        if isinstance(value, dict):
            return value
    return {}


def coerce_mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def normalize_ai_runtime_mapping(mapping: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(mapping, dict):
        return {}

    normalized: Dict[str, Any] = {}
    for target_key, *source_keys in (
        ("MODEL", "MODEL", "model"),
        ("API_KEY", "API_KEY", "api_key"),
        ("API_BASE", "API_BASE", "api_base"),
        ("PROVIDER_FAMILY", "PROVIDER_FAMILY", "provider_family"),
        ("TIMEOUT", "TIMEOUT", "timeout"),
        ("TEMPERATURE", "TEMPERATURE", "temperature"),
        ("MAX_TOKENS", "MAX_TOKENS", "max_tokens"),
        ("NUM_RETRIES", "NUM_RETRIES", "num_retries"),
    ):
        value = mapping_get(mapping, *source_keys)
        if value not in (None, ""):
            normalized[target_key] = value

    extra_params = mapping_get(mapping, "EXTRA_PARAMS", "extra_params")
    if isinstance(extra_params, dict):
        normalized["EXTRA_PARAMS"] = dict(extra_params)

    return normalized


def normalize_ai_operation_mapping(mapping: Dict[str, Any]) -> Dict[str, Any]:
    normalized = normalize_ai_runtime_mapping(mapping)
    if not isinstance(mapping, dict):
        return normalized

    for target_key, *source_keys in (
        ("PROMPT_FILE", "PROMPT_FILE", "prompt_file"),
        ("ITEM_PROMPT_FILE", "ITEM_PROMPT_FILE", "item_prompt_file"),
        ("REPORT_PROMPT_FILE", "REPORT_PROMPT_FILE", "report_prompt_file"),
        ("EXTRACT_PROMPT_FILE", "EXTRACT_PROMPT_FILE", "extract_prompt_file"),
        ("UPDATE_TAGS_PROMPT_FILE", "UPDATE_TAGS_PROMPT_FILE", "update_tags_prompt_file"),
    ):
        value = mapping_get(mapping, *source_keys)
        if value not in (None, ""):
            normalized[target_key] = value
    runtime_cache = normalize_runtime_cache_mapping(
        get_nested_mapping(mapping, "RUNTIME_CACHE", "runtime_cache")
        or get_nested_mapping(mapping, "LLM_CACHE", "llm_cache")
    )
    if runtime_cache:
        normalized["RUNTIME_CACHE"] = runtime_cache
    return normalized


def normalize_insight_content_mapping(mapping: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(mapping, dict):
        mapping = {}
    extractor_order = mapping_get(mapping, "EXTRACTOR_ORDER", "extractor_order", default=None)
    if isinstance(extractor_order, str):
        extractor_order = [extractor_order]
    if not isinstance(extractor_order, list) or not extractor_order:
        extractor_order = ["trafilatura", "readability", "beautifulsoup"]
    return {
        "ENABLED": bool(mapping_get(mapping, "ENABLED", "enabled", default=False)),
        "FETCH_TIMEOUT_SECONDS": int(mapping_get(mapping, "FETCH_TIMEOUT_SECONDS", "fetch_timeout_seconds", default=8) or 8),
        "FETCH_CONCURRENCY": int(mapping_get(mapping, "FETCH_CONCURRENCY", "fetch_concurrency", default=3) or 3),
        "MAX_RAW_CHARS": int(mapping_get(mapping, "MAX_RAW_CHARS", "max_raw_chars", default=120000) or 120000),
        "MAX_REDUCED_CHARS": int(mapping_get(mapping, "MAX_REDUCED_CHARS", "max_reduced_chars", default=6000) or 6000),
        "EXTRACTOR_ORDER": [str(item) for item in extractor_order if str(item).strip()],
    }


def normalize_insight_summary_mapping(mapping: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(mapping, dict):
        mapping = {}
    return {
        "ITEM_PROMPT_FILE": str(
            mapping_get(mapping, "ITEM_PROMPT_FILE", "item_prompt_file", default="insight/item_summary_prompt.txt")
            or "insight/item_summary_prompt.txt"
        ),
        "REPORT_PROMPT_FILE": str(
            mapping_get(mapping, "REPORT_PROMPT_FILE", "report_prompt_file", default="insight/report_summary_prompt.txt")
            or "insight/report_summary_prompt.txt"
        ),
        "ITEM_CONCURRENCY": int(mapping_get(mapping, "ITEM_CONCURRENCY", "item_concurrency", default=3) or 3),
        "ITEM_SUMMARY_MAX_CHARS": int(
            mapping_get(mapping, "ITEM_SUMMARY_MAX_CHARS", "item_summary_max_chars", default=220) or 220
        ),
        "REPORT_SUMMARY_MAX_CHARS": int(
            mapping_get(mapping, "REPORT_SUMMARY_MAX_CHARS", "report_summary_max_chars", default=300) or 300
        ),
    }


def merge_ai_runtime_config(base_config: Dict[str, Any], override_config: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base_config or {})
    merged.update(normalize_ai_runtime_mapping(override_config))
    return merged


def normalize_runtime_cache_mapping(mapping: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(mapping, dict) or not mapping:
        return {}
    return {
        "ENABLED": bool(mapping_get(mapping, "ENABLED", "enabled", default=True)),
        "TTL_SECONDS": int(mapping_get(mapping, "TTL_SECONDS", "ttl_seconds", default=3600) or 3600),
        "MAX_ENTRIES": int(mapping_get(mapping, "MAX_ENTRIES", "max_entries", default=512) or 512),
    }


def workflow_config(config: Dict[str, Any], raw_config: Dict[str, Any]) -> Dict[str, Any]:
    workflow = config.get("WORKFLOW", {})
    if isinstance(workflow, dict) and workflow:
        return workflow
    workflow = raw_config.get("workflow", {})
    return workflow if isinstance(workflow, dict) else {}


def raw_ai_config(raw_config: Dict[str, Any]) -> Dict[str, Any]:
    ai = raw_config.get("ai", {})
    return ai if isinstance(ai, dict) else {}


def get_workflow_stage(config: Dict[str, Any], raw_config: Dict[str, Any], *names: str) -> Dict[str, Any]:
    workflow = workflow_config(config, raw_config)
    for name in names:
        value = workflow.get(name)
        if isinstance(value, dict) and value:
            return value
    return {}


def resolve_platforms(config: Dict[str, Any], raw_config: Dict[str, Any]) -> list[Dict[str, Any]]:
    platforms = config.get("PLATFORMS", [])
    if isinstance(platforms, list) and platforms:
        return [dict(platform) for platform in platforms if isinstance(platform, dict)]

    legacy_platforms = get_nested_mapping(raw_config, "platforms")
    legacy_sources = legacy_platforms.get("sources", [])
    if isinstance(legacy_sources, list):
        return [dict(platform) for platform in legacy_sources if isinstance(platform, dict)]
    return []


def resolve_display_config(config: Dict[str, Any], raw_config: Dict[str, Any]) -> Dict[str, Any]:
    display = config.get("DISPLAY", {})
    if isinstance(display, dict) and display:
        return {
            "REGION_ORDER": list(display.get("REGION_ORDER", DEFAULT_REGION_ORDER)),
            "REGIONS": coerce_mapping(display.get("REGIONS", {})),
            "STANDALONE": coerce_mapping(display.get("STANDALONE", {})),
        }

    legacy_display = coerce_mapping(raw_config.get("display", {}))
    if not legacy_display:
        return {
            "REGION_ORDER": list(DEFAULT_REGION_ORDER),
            "REGIONS": {},
            "STANDALONE": {},
        }

    legacy_regions = coerce_mapping(legacy_display.get("regions", {}))
    legacy_standalone = coerce_mapping(legacy_display.get("standalone", {}))
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


def resolve_storage_config(config: Dict[str, Any], raw_config: Dict[str, Any]) -> Dict[str, Any]:
    storage = config.get("STORAGE", {})
    if isinstance(storage, dict) and storage:
        return {
            "BACKEND": str(storage.get("BACKEND", "local") or "local"),
            "FORMATS": coerce_mapping(storage.get("FORMATS", {})),
            "LOCAL": coerce_mapping(storage.get("LOCAL", {})),
        }

    legacy_storage = coerce_mapping(raw_config.get("storage", {}))
    legacy_formats = coerce_mapping(legacy_storage.get("formats", {}))
    legacy_local = coerce_mapping(legacy_storage.get("local", {}))
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


def resolve_ai_runtime_config(config: Dict[str, Any], raw_config: Dict[str, Any]) -> Dict[str, Any]:
    configured = config.get("AI", {})
    if isinstance(configured, dict) and configured:
        return configured
    return normalize_ai_runtime_mapping(get_nested_mapping(raw_ai_config(raw_config), "RUNTIME", "runtime"))


def resolve_ai_operation_mapping(
    config: Dict[str, Any],
    raw_config: Dict[str, Any],
    operation_name: str,
    *,
    legacy_key: str | None = None,
) -> Dict[str, Any]:
    operations = get_nested_mapping(raw_ai_config(raw_config), "OPERATIONS", "operations")
    operation = get_nested_mapping(
        operations,
        operation_name,
        operation_name.lower(),
        operation_name.upper(),
    )
    merged: Dict[str, Any] = {}
    if legacy_key:
        legacy_config = config.get(legacy_key, {})
        if isinstance(legacy_config, dict):
            merged.update(legacy_config)
    merged.update(operation)
    merged.update(normalize_ai_operation_mapping(operation))
    return merged


def resolve_selection_stage_config(config: Dict[str, Any], raw_config: Dict[str, Any]) -> Dict[str, Any]:
    workflow_selection = get_workflow_stage(config, raw_config, "SELECTION", "selection")
    if workflow_selection:
        workflow_ai = get_nested_mapping(workflow_selection, "AI", "ai")
        workflow_semantic = get_nested_mapping(workflow_selection, "SEMANTIC", "semantic")
        return {
            "STRATEGY": str(mapping_get(workflow_selection, "STRATEGY", "strategy", default="keyword") or "keyword"),
            "FREQUENCY_FILE": mapping_get(workflow_selection, "FREQUENCY_FILE", "frequency_file"),
            "PRIORITY_SORT_ENABLED": bool(
                mapping_get(workflow_selection, "PRIORITY_SORT_ENABLED", "priority_sort_enabled", default=False)
            ),
            "AI": {
                "INTERESTS_FILE": mapping_get(workflow_ai, "INTERESTS_FILE", "interests_file"),
                "BATCH_SIZE": int(mapping_get(workflow_ai, "BATCH_SIZE", "batch_size", default=200) or 200),
                "BATCH_INTERVAL": float(mapping_get(workflow_ai, "BATCH_INTERVAL", "batch_interval", default=5) or 0),
                "CONCURRENCY": int(mapping_get(workflow_ai, "CONCURRENCY", "concurrency", default=3) or 3),
                "MIN_SCORE": float(mapping_get(workflow_ai, "MIN_SCORE", "min_score", default=0) or 0),
                "RECLASSIFY_THRESHOLD": float(
                    mapping_get(workflow_ai, "RECLASSIFY_THRESHOLD", "reclassify_threshold", default=0.6) or 0.6
                ),
                "FALLBACK_TO_KEYWORD": bool(
                    mapping_get(workflow_ai, "FALLBACK_TO_KEYWORD", "fallback_to_keyword", default=True)
                ),
            },
            "SEMANTIC": {
                "ENABLED": bool(mapping_get(workflow_semantic, "ENABLED", "enabled", default=True)),
                "TOP_K": int(mapping_get(workflow_semantic, "TOP_K", "top_k", default=3) or 3),
                "MIN_SCORE": float(mapping_get(workflow_semantic, "MIN_SCORE", "min_score", default=0.55) or 0.55),
                "DIRECT_THRESHOLD": float(
                    mapping_get(workflow_semantic, "DIRECT_THRESHOLD", "direct_threshold", default=0.78) or 0.78
                ),
            },
        }

    filter_config = config.get("FILTER", {})
    ai_filter_config = config.get("AI_FILTER", {})
    return {
        "STRATEGY": str(filter_config.get("METHOD", "keyword") or "keyword"),
        "FREQUENCY_FILE": filter_config.get("FREQUENCY_FILE"),
        "PRIORITY_SORT_ENABLED": bool(filter_config.get("PRIORITY_SORT_ENABLED", False)),
        "AI": {
            "INTERESTS_FILE": ai_filter_config.get("INTERESTS_FILE"),
            "BATCH_SIZE": int(ai_filter_config.get("BATCH_SIZE", 200) or 200),
            "BATCH_INTERVAL": float(ai_filter_config.get("BATCH_INTERVAL", 5) or 0),
            "CONCURRENCY": int(ai_filter_config.get("CONCURRENCY", 3) or 3),
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


def resolve_insight_stage_config(config: Dict[str, Any], raw_config: Dict[str, Any]) -> Dict[str, Any]:
    workflow_insight = get_workflow_stage(config, raw_config, "INSIGHT", "insight")
    if workflow_insight:
        enabled = bool(mapping_get(workflow_insight, "ENABLED", "enabled", default=False))
        content = get_nested_mapping(workflow_insight, "CONTENT", "content")
        summary = get_nested_mapping(workflow_insight, "SUMMARY", "summary")
        return {
            "ENABLED": enabled,
            "STRATEGY": str(
                mapping_get(workflow_insight, "STRATEGY", "strategy", default="ai" if enabled else "noop")
                or ("ai" if enabled else "noop")
            ),
            "MODE": str(mapping_get(workflow_insight, "MODE", "mode", default="follow_report") or "follow_report"),
            "MAX_ITEMS": int(mapping_get(workflow_insight, "MAX_ITEMS", "max_items", default=50) or 50),
            "LANGUAGE": str(mapping_get(workflow_insight, "LANGUAGE", "language", default="Chinese") or "Chinese"),
            "CONTENT": normalize_insight_content_mapping(content),
            "SUMMARY": normalize_insight_summary_mapping(summary),
        }

    analysis_config = config.get("AI_ANALYSIS", {})
    enabled = bool(analysis_config.get("ENABLED", False))
    return {
        "ENABLED": enabled,
        "STRATEGY": str(analysis_config.get("STRATEGY", "ai" if enabled else "noop") or ("ai" if enabled else "noop")),
        "MODE": str(analysis_config.get("MODE", "follow_report") or "follow_report"),
        "MAX_ITEMS": int(analysis_config.get("MAX_ITEMS", 50) or 50),
        "LANGUAGE": str(analysis_config.get("LANGUAGE", "Chinese") or "Chinese"),
        "CONTENT": normalize_insight_content_mapping(coerce_mapping(analysis_config.get("CONTENT", {}))),
        "SUMMARY": normalize_insight_summary_mapping(coerce_mapping(analysis_config.get("SUMMARY", {}))),
    }


def resolve_ai_filter_config(config: Dict[str, Any], raw_config: Dict[str, Any]) -> Dict[str, Any]:
    selection_ai = resolve_selection_stage_config(config, raw_config).get("AI", {})
    operation = resolve_ai_operation_mapping(config, raw_config, "selection", legacy_key="AI_FILTER")
    return {
        "BATCH_SIZE": int(selection_ai.get("BATCH_SIZE", 200) or 200),
        "BATCH_INTERVAL": float(selection_ai.get("BATCH_INTERVAL", 5) or 0),
        "CONCURRENCY": int(selection_ai.get("CONCURRENCY", 3) or 3),
        "TIMEOUT": mapping_get(operation, "TIMEOUT", "timeout"),
        "NUM_RETRIES": mapping_get(operation, "NUM_RETRIES", "num_retries"),
        "EXTRA_PARAMS": coerce_mapping(mapping_get(operation, "EXTRA_PARAMS", "extra_params", default={})),
        "RUNTIME_CACHE": normalize_runtime_cache_mapping(
            get_nested_mapping(operation, "RUNTIME_CACHE", "runtime_cache")
            or get_nested_mapping(operation, "LLM_CACHE", "llm_cache")
        ),
        "INTERESTS_FILE": selection_ai.get("INTERESTS_FILE"),
        "PROMPT_FILE": str(mapping_get(operation, "PROMPT_FILE", "prompt_file", default="prompt.txt") or "prompt.txt"),
        "EXTRACT_PROMPT_FILE": str(
            mapping_get(operation, "EXTRACT_PROMPT_FILE", "extract_prompt_file", default="extract_prompt.txt")
            or "extract_prompt.txt"
        ),
        "UPDATE_TAGS_PROMPT_FILE": str(
            mapping_get(
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


def resolve_ai_analysis_config(config: Dict[str, Any], raw_config: Dict[str, Any]) -> Dict[str, Any]:
    insight = resolve_insight_stage_config(config, raw_config)
    operation = resolve_ai_operation_mapping(config, raw_config, "insight", legacy_key="AI_ANALYSIS")
    summary = normalize_insight_summary_mapping(insight.get("SUMMARY", {}))
    item_prompt = mapping_get(operation, "ITEM_PROMPT_FILE", "item_prompt_file")
    report_prompt = mapping_get(operation, "REPORT_PROMPT_FILE", "report_prompt_file")
    if item_prompt:
        summary["ITEM_PROMPT_FILE"] = str(item_prompt)
    if report_prompt:
        summary["REPORT_PROMPT_FILE"] = str(report_prompt)
    return {
        "ENABLED": bool(insight.get("ENABLED", False)),
        "STRATEGY": str(insight.get("STRATEGY", "noop") or "noop"),
        "LANGUAGE": str(insight.get("LANGUAGE", "Chinese") or "Chinese"),
        "PROMPT_FILE": str(mapping_get(operation, "PROMPT_FILE", "prompt_file", default="global_insight_prompt.txt") or "global_insight_prompt.txt"),
        "MODE": str(insight.get("MODE", "follow_report") or "follow_report"),
        "MAX_ITEMS": int(insight.get("MAX_ITEMS", 50) or 50),
        "TIMEOUT": mapping_get(operation, "TIMEOUT", "timeout"),
        "NUM_RETRIES": mapping_get(operation, "NUM_RETRIES", "num_retries"),
        "EXTRA_PARAMS": coerce_mapping(mapping_get(operation, "EXTRA_PARAMS", "extra_params", default={})),
        "RUNTIME_CACHE": normalize_runtime_cache_mapping(
            get_nested_mapping(operation, "RUNTIME_CACHE", "runtime_cache")
            or get_nested_mapping(operation, "LLM_CACHE", "llm_cache")
        ),
        "CONTENT": normalize_insight_content_mapping(insight.get("CONTENT", {})),
        "SUMMARY": summary,
    }


def resolve_ai_filter_model_config(config: Dict[str, Any], raw_config: Dict[str, Any]) -> Dict[str, Any]:
    configured = config.get("AI_FILTER_MODEL", {})
    if isinstance(configured, dict) and configured:
        return configured
    return merge_ai_runtime_config(
        resolve_ai_runtime_config(config, raw_config),
        resolve_ai_operation_mapping(config, raw_config, "selection", legacy_key="AI_FILTER"),
    )


def resolve_ai_analysis_model_config(config: Dict[str, Any], raw_config: Dict[str, Any]) -> Dict[str, Any]:
    configured = config.get("AI_ANALYSIS_MODEL", {})
    if isinstance(configured, dict) and configured:
        return configured
    return merge_ai_runtime_config(
        resolve_ai_runtime_config(config, raw_config),
        resolve_ai_operation_mapping(config, raw_config, "insight", legacy_key="AI_ANALYSIS"),
    )


def normalize_runtime_config(config: Dict[str, Any] | None, raw_config: Dict[str, Any] | None = None) -> Dict[str, Any]:
    base_config = deepcopy(config) if isinstance(config, dict) else {}
    raw = deepcopy(raw_config) if isinstance(raw_config, dict) else deepcopy(base_config)

    base_config["PLATFORMS"] = resolve_platforms(base_config, raw)
    base_config["DISPLAY"] = resolve_display_config(base_config, raw)
    base_config["STORAGE"] = resolve_storage_config(base_config, raw)
    base_config["WORKFLOW"] = {
        "SELECTION": resolve_selection_stage_config(base_config, raw),
        "INSIGHT": resolve_insight_stage_config(base_config, raw),
    }
    base_config["AI"] = resolve_ai_runtime_config(base_config, raw)
    base_config["AI_FILTER"] = resolve_ai_filter_config(base_config, raw)
    base_config["AI_ANALYSIS"] = resolve_ai_analysis_config(base_config, raw)
    base_config["AI_FILTER_MODEL"] = resolve_ai_filter_model_config(base_config, raw)
    base_config["AI_ANALYSIS_MODEL"] = resolve_ai_analysis_model_config(base_config, raw)
    base_config["FILTER"] = {
        "METHOD": base_config["WORKFLOW"]["SELECTION"].get("STRATEGY", "keyword"),
        "FREQUENCY_FILE": base_config["WORKFLOW"]["SELECTION"].get("FREQUENCY_FILE"),
        "PRIORITY_SORT_ENABLED": bool(
            base_config["WORKFLOW"]["SELECTION"].get("PRIORITY_SORT_ENABLED", False)
        ),
    }
    return base_config
