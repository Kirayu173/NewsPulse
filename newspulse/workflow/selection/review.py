# coding=utf-8
"""Stage-4 review exporter for the native selection funnel."""

from __future__ import annotations

import argparse
import copy
import json
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from newspulse.context import AppContext
from newspulse.core import load_config
from newspulse.crawler.fetcher import DataFetcher
from newspulse.crawler.models import CrawlSourceSpec
from newspulse.crawler.source_names import resolve_source_display_name
from newspulse.storage import normalize_crawl_batch
from newspulse.utils.time import DEFAULT_TIMEZONE
from newspulse.workflow.shared.contracts import HotlistSnapshot, SelectionRejectedItem, SelectionResult
from newspulse.workflow.shared.options import SnapshotOptions


REVIEW_FILE_ENCODING = "utf-8-sig"


def _write_review_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding=REVIEW_FILE_ENCODING)


def _build_source_specs(platforms: Sequence[dict]) -> list[CrawlSourceSpec]:
    return [
        CrawlSourceSpec(
            source_id=str(platform["id"]),
            source_name=resolve_source_display_name(
                str(platform["id"]),
                str(platform.get("name", "") or ""),
            ),
        )
        for platform in platforms
        if platform.get("id")
    ]


def _snapshot_summary(snapshot: HotlistSnapshot) -> dict[str, object]:
    return {
        "mode": snapshot.mode,
        "generated_at": snapshot.generated_at,
        "item_count": len(snapshot.items),
        "new_item_count": len(snapshot.new_items),
        "failed_source_count": len(snapshot.failed_sources),
        "standalone_section_count": len(snapshot.standalone_sections),
        "summary": dict(snapshot.summary),
    }


def _selected_items(selection: SelectionResult | None) -> list[Any]:
    if selection is None:
        return []
    return list(selection.qualified_items or selection.selected_items or [])


def _serialize_rejected_item(item: SelectionRejectedItem) -> dict[str, Any]:
    return {
        "news_item_id": item.news_item_id,
        "source_id": item.source_id,
        "source_name": item.source_name,
        "title": item.title,
        "rejected_stage": item.rejected_stage,
        "rejected_reason": item.rejected_reason,
        "score": item.score,
        "metadata": dict(item.metadata or {}),
    }


def _filter_rejected_items(selection: SelectionResult | None, stage: str) -> list[dict[str, Any]]:
    if selection is None:
        return []
    return [
        _serialize_rejected_item(item)
        for item in selection.rejected_items
        if str(item.rejected_stage or "").strip() == stage
    ]


def _selection_summary(selection: SelectionResult | None, *, skipped: bool = False, reason: str = "") -> dict[str, object]:
    if selection is None:
        return {
            "strategy": "ai" if skipped else "",
            "skipped": skipped,
            "reason": reason,
            "total_candidates": 0,
            "total_selected": 0,
            "qualified_count": 0,
            "rejected_count": 0,
            "selected_new_count": 0,
            "diagnostics": {},
        }

    return {
        "strategy": selection.strategy,
        "skipped": skipped,
        "reason": reason,
        "total_candidates": selection.total_candidates,
        "total_selected": selection.total_selected,
        "qualified_count": len(_selected_items(selection)),
        "rejected_count": len(selection.rejected_items),
        "selected_new_count": len(selection.selected_new_items),
        "diagnostics": dict(selection.diagnostics),
    }


def _mapping_list(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in value if isinstance(item, Mapping)] if isinstance(value, Sequence) else []


def _build_selection_item_index(selection: SelectionResult | None) -> dict[str, dict[str, Any]]:
    if selection is None:
        return {}

    index: dict[str, dict[str, Any]] = {}
    for item in selection.selected_items:
        item_id = str(getattr(item, "news_item_id", "") or "").strip()
        if not item_id:
            continue
        index[item_id] = {
            "news_item_id": item_id,
            "source_id": str(getattr(item, "source_id", "") or ""),
            "source_name": str(getattr(item, "source_name", "") or ""),
            "title": str(getattr(item, "title", "") or ""),
            "current_rank": int(getattr(item, "current_rank", 0) or 0),
        }

    for item in selection.rejected_items:
        item_id = str(item.news_item_id or "").strip()
        if not item_id:
            continue
        index.setdefault(
            item_id,
            {
                "news_item_id": item_id,
                "source_id": str(item.source_id or ""),
                "source_name": str(item.source_name or ""),
                "title": str(item.title or ""),
                "current_rank": int(item.metadata.get("current_rank", 0) or 0),
            },
        )
    return index


def _extract_semantic_payload(selection: SelectionResult | None, *, skipped_reason: str = "") -> dict[str, Any]:
    if selection is None:
        return {
            "enabled": False,
            "skipped": True,
            "reason": skipped_reason or "ai_selection_unavailable",
            "model": "",
            "topic_count": 0,
            "candidate_count": 0,
            "passed_count": 0,
            "rejected_count": 0,
            "topics": [],
            "candidates": [],
            "rejected_items": [],
        }

    diagnostics = dict(selection.diagnostics)
    topics = _mapping_list(diagnostics.get("semantic_topics"))
    candidates = _mapping_list(diagnostics.get("semantic_candidates"))
    rejected_items = _filter_rejected_items(selection, "semantic")
    return {
        "enabled": bool(diagnostics.get("semantic_enabled", False)),
        "skipped": bool(diagnostics.get("semantic_skipped", False)),
        "reason": str(diagnostics.get("semantic_reason", "") or ""),
        "model": str(diagnostics.get("semantic_model", "") or ""),
        "topic_count": int(diagnostics.get("semantic_topic_count", len(topics)) or len(topics)),
        "candidate_count": int(diagnostics.get("semantic_candidate_count", len(candidates)) or len(candidates)),
        "passed_count": int(diagnostics.get("semantic_passed_count", 0) or 0),
        "rejected_count": int(diagnostics.get("semantic_rejected_count", len(rejected_items)) or len(rejected_items)),
        "topics": topics,
        "candidates": candidates,
        "rejected_items": rejected_items,
    }


def _semantic_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "enabled": bool(payload.get("enabled", False)),
        "skipped": bool(payload.get("skipped", False)),
        "reason": str(payload.get("reason", "") or ""),
        "model": str(payload.get("model", "") or ""),
        "topic_count": int(payload.get("topic_count", 0) or 0),
        "candidate_count": int(payload.get("candidate_count", 0) or 0),
        "passed_count": int(payload.get("passed_count", 0) or 0),
        "rejected_count": int(payload.get("rejected_count", 0) or 0),
    }


def _extract_llm_payload(selection: SelectionResult | None, *, skipped_reason: str = "") -> dict[str, Any]:
    if selection is None:
        return {
            "enabled": False,
            "skipped": True,
            "reason": skipped_reason or "ai_selection_unavailable",
            "batch_count": 0,
            "evaluated_count": 0,
            "kept_count": 0,
            "rejected_count": 0,
            "min_score": 0.0,
            "focus_labels": [],
            "decisions": [],
            "kept_matches": [],
            "rejected_items": [],
        }

    diagnostics = dict(selection.diagnostics)
    item_index = _build_selection_item_index(selection)
    decisions = []
    for decision in _mapping_list(diagnostics.get("llm_decisions")):
        news_item_id = str(decision.get("news_item_id", "") or "").strip()
        item = item_index.get(news_item_id, {})
        metadata = dict(decision.get("metadata", {})) if isinstance(decision.get("metadata"), Mapping) else {}
        quality_score = float(decision.get("quality_score", decision.get("score", 0.0)) or 0.0)
        decisions.append(
            {
                **decision,
                "news_item_id": news_item_id,
                "score": quality_score,
                "quality_score": quality_score,
                "source_id": str(item.get("source_id", "") or metadata.get("source_id", "") or ""),
                "source_name": str(item.get("source_name", "") or metadata.get("source_name", "") or ""),
                "title": str(item.get("title", "") or ""),
                "current_rank": int(item.get("current_rank", 0) or 0),
                "metadata": metadata,
            }
        )
    kept_matches = [
        match
        for match in _mapping_list(diagnostics.get("selected_matches"))
        if str(match.get("decision_layer", "")).strip() == "llm_quality_gate"
    ]
    rejected_items = _filter_rejected_items(selection, "llm")
    focus_labels = diagnostics.get("focus_labels", [])
    if not isinstance(focus_labels, list):
        focus_labels = []
    return {
        "enabled": True,
        "skipped": False,
        "reason": "",
        "batch_count": int(diagnostics.get("llm_batch_count", 0) or 0),
        "evaluated_count": int(diagnostics.get("llm_evaluated_count", len(decisions)) or len(decisions)),
        "kept_count": len(kept_matches),
        "rejected_count": len(rejected_items),
        "min_score": float(diagnostics.get("min_score", 0.0) or 0.0),
        "focus_labels": [str(label) for label in focus_labels if str(label).strip()],
        "decisions": decisions,
        "kept_matches": kept_matches,
        "rejected_items": rejected_items,
    }


def _llm_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "enabled": bool(payload.get("enabled", False)),
        "skipped": bool(payload.get("skipped", False)),
        "reason": str(payload.get("reason", "") or ""),
        "batch_count": int(payload.get("batch_count", 0) or 0),
        "evaluated_count": int(payload.get("evaluated_count", 0) or 0),
        "kept_count": int(payload.get("kept_count", 0) or 0),
        "rejected_count": int(payload.get("rejected_count", 0) or 0),
        "min_score": float(payload.get("min_score", 0.0) or 0.0),
    }


def _append_result_section(lines: list[str], title: str, selection: SelectionResult | None, *, skipped: bool = False, reason: str = "") -> None:
    lines.append(f"## {title}")
    lines.append("")
    if selection is None:
        lines.append(f"- skipped: {str(skipped).lower()}")
        if reason:
            lines.append(f"- reason: {reason}")
        lines.append("")
        return

    selected_items = _selected_items(selection)
    lines.append(f"- strategy: `{selection.strategy}`")
    lines.append(f"- total_candidates: {selection.total_candidates}")
    lines.append(f"- total_selected: {selection.total_selected}")
    lines.append(f"- qualified_count: {len(selected_items)}")
    lines.append(f"- rejected_count: {len(selection.rejected_items)}")
    lines.append(f"- selected_new_count: {len(selection.selected_new_items)}")
    lines.append("")
    lines.append("### Qualified Preview")
    lines.append("")
    for index, item in enumerate(selected_items[:12], start=1):
        lines.append(f"{index}. [{item.source_id}] [{item.current_rank}] {item.title}")
    if len(selected_items) > 12:
        lines.append(f"... ({len(selected_items) - 12} more qualified items)")
    lines.append("")
    if selection.rejected_items:
        lines.append("### Rejected Preview")
        lines.append("")
        for index, item in enumerate(selection.rejected_items[:12], start=1):
            lines.append(
                f"{index}. [{item.source_id}] {item.title} -> {item.rejected_stage}: {item.rejected_reason}"
            )
        if len(selection.rejected_items) > 12:
            lines.append(f"... ({len(selection.rejected_items) - 12} more rejected items)")
        lines.append("")


def _append_semantic_section(lines: list[str], semantic_payload: Mapping[str, Any]) -> None:
    lines.append("## \u8bed\u4e49\u53ec\u56de\uff08Semantic Recall\uff09")
    lines.append("")
    lines.append(f"- enabled: {str(bool(semantic_payload.get('enabled'))).lower()}")
    lines.append(f"- skipped: {str(bool(semantic_payload.get('skipped'))).lower()}")
    reason = str(semantic_payload.get("reason", "") or "").strip()
    if reason:
        lines.append(f"- reason: {reason}")
    model = str(semantic_payload.get("model", "") or "").strip()
    if model:
        lines.append(f"- model: `{model}`")
    lines.append(f"- topic_count: {int(semantic_payload.get('topic_count', 0) or 0)}")
    lines.append(f"- candidate_count: {int(semantic_payload.get('candidate_count', 0) or 0)}")
    lines.append(f"- passed_count: {int(semantic_payload.get('passed_count', 0) or 0)}")
    lines.append(f"- rejected_count: {int(semantic_payload.get('rejected_count', 0) or 0)}")
    lines.append("")

    topics = _mapping_list(semantic_payload.get("topics"))
    if topics:
        lines.append("### Topic Catalog")
        lines.append("")
        for topic in topics[:10]:
            label = str(topic.get("label", "")).strip() or str(topic.get("topic_id", "")).strip()
            description = str(topic.get("description", "")).strip()
            line = f"- `{label}`"
            if description:
                line += f": {description}"
            lines.append(line)
        if len(topics) > 10:
            lines.append(f"... ({len(topics) - 10} more topics)")
        lines.append("")

    candidates = sorted(
        _mapping_list(semantic_payload.get("candidates")),
        key=lambda row: (-float(row.get("score", 0.0) or 0.0), str(row.get("news_item_id", ""))),
    )
    if candidates:
        lines.append("### Candidate Preview")
        lines.append("")
        for index, candidate in enumerate(candidates[:12], start=1):
            title = str(candidate.get("title", "")).strip()
            source_id = str(candidate.get("source_id", "")).strip()
            topic_label = str(candidate.get("topic_label", "")).strip()
            score = float(candidate.get("score", 0.0) or 0.0)
            lines.append(f"{index}. [{source_id}] {title} -> {topic_label} (score={score:.4f})")
        if len(candidates) > 12:
            lines.append(f"... ({len(candidates) - 12} more semantic candidates)")
        lines.append("")

    rejected_items = _mapping_list(semantic_payload.get("rejected_items"))
    if rejected_items:
        lines.append("### Rejected by Semantic")
        lines.append("")
        for index, item in enumerate(rejected_items[:12], start=1):
            lines.append(
                f"{index}. [{item.get('source_id', '')}] {item.get('title', '')} -> {item.get('rejected_reason', '')}"
            )
        if len(rejected_items) > 12:
            lines.append(f"... ({len(rejected_items) - 12} more semantic rejections)")
        lines.append("")


def _append_llm_section(lines: list[str], llm_payload: Mapping[str, Any]) -> None:
    lines.append("## LLM \u8d28\u91cf\u95f8\u95e8\uff08LLM Quality Gate\uff09")
    lines.append("")
    lines.append(f"- enabled: {str(bool(llm_payload.get('enabled'))).lower()}")
    lines.append(f"- skipped: {str(bool(llm_payload.get('skipped'))).lower()}")
    reason = str(llm_payload.get("reason", "") or "").strip()
    if reason:
        lines.append(f"- reason: {reason}")
    lines.append(f"- batch_count: {int(llm_payload.get('batch_count', 0) or 0)}")
    lines.append(f"- evaluated_count: {int(llm_payload.get('evaluated_count', 0) or 0)}")
    lines.append(f"- kept_count: {int(llm_payload.get('kept_count', 0) or 0)}")
    lines.append(f"- rejected_count: {int(llm_payload.get('rejected_count', 0) or 0)}")
    lines.append(f"- min_score: {float(llm_payload.get('min_score', 0.0) or 0.0):.2f}")
    focus_labels = llm_payload.get("focus_labels", [])
    if isinstance(focus_labels, list) and focus_labels:
        lines.append(f"- focus_labels: {', '.join(str(label) for label in focus_labels)}")
    lines.append("")

    kept_matches = _mapping_list(llm_payload.get("kept_matches"))
    if kept_matches:
        lines.append("### Kept by LLM")
        lines.append("")
        for index, match in enumerate(kept_matches[:12], start=1):
            lines.append(
                f"{index}. [{match.get('source_id', '')}] {match.get('title', '')} "
                f"(score={float(match.get('quality_score', 0.0) or 0.0):.4f})"
            )
        if len(kept_matches) > 12:
            lines.append(f"... ({len(kept_matches) - 12} more llm-kept items)")
        lines.append("")

    rejected_items = _mapping_list(llm_payload.get("rejected_items"))
    if rejected_items:
        lines.append("### Rejected by LLM")
        lines.append("")
        for index, item in enumerate(rejected_items[:12], start=1):
            lines.append(
                f"{index}. [{item.get('source_id', '')}] {item.get('title', '')} -> {item.get('rejected_reason', '')}"
            )
        if len(rejected_items) > 12:
            lines.append(f"... ({len(rejected_items) - 12} more llm rejections)")
        lines.append("")


def _build_selection_review_markdown(
    *,
    generated_at: datetime,
    config_path: Path,
    storage_data_dir: Path,
    snapshot: HotlistSnapshot,
    keyword_selection: SelectionResult,
    ai_selection: SelectionResult | None,
    ai_skip_reason: str,
    semantic_payload: Mapping[str, Any],
    llm_payload: Mapping[str, Any],
) -> str:
    lines: list[str] = []
    lines.append("# Stage 4 Selection Review")
    lines.append("")
    lines.append(f"- generated_at: {generated_at.strftime('%Y-%m-%d %H:%M:%S %z')}")
    lines.append(f"- config_path: `{config_path}`")
    lines.append(f"- storage_data_dir: `{storage_data_dir}`")
    lines.append(f"- snapshot_mode: `{snapshot.mode}`")
    lines.append(f"- snapshot_generated_at: `{snapshot.generated_at}`")
    lines.append(f"- snapshot_item_count: {len(snapshot.items)}")
    lines.append(f"- snapshot_new_item_count: {len(snapshot.new_items)}")
    lines.append(f"- snapshot_failed_source_count: {len(snapshot.failed_sources)}")
    lines.append("")
    lines.append("## Snapshot Preview")
    lines.append("")
    for index, item in enumerate(snapshot.items[:20], start=1):
        lines.append(f"{index}. [{item.source_id}] [{item.current_rank}] {item.title}")
    if len(snapshot.items) > 20:
        lines.append(f"... ({len(snapshot.items) - 20} more items)")
    lines.append("")

    _append_result_section(lines, "\u89c4\u5219\u8fc7\u6ee4\uff08Rule Filter\uff09", keyword_selection)
    _append_semantic_section(lines, semantic_payload)
    _append_llm_section(lines, llm_payload)
    _append_result_section(
        lines,
        "\u6700\u7ec8\u7ed3\u679c\uff08Final Selection\uff09",
        ai_selection,
        skipped=ai_selection is None,
        reason=ai_skip_reason,
    )
    return "\n".join(lines)


def export_selection_outbox(
    *,
    outbox_dir: str | Path,
    generated_at: datetime,
    config_path: str | Path,
    storage_data_dir: str | Path,
    snapshot: HotlistSnapshot,
    keyword_selection: SelectionResult,
    ai_selection: SelectionResult | None,
    ai_skip_reason: str,
    run_log: str,
) -> dict[str, object]:
    outbox_path = Path(outbox_dir)
    outbox_path.mkdir(parents=True, exist_ok=True)
    config_path_obj = Path(config_path)
    storage_path = Path(storage_data_dir)
    semantic_payload = _extract_semantic_payload(ai_selection, skipped_reason=ai_skip_reason)
    llm_payload = _extract_llm_payload(ai_selection, skipped_reason=ai_skip_reason)

    summary = {
        "generated_at": generated_at.isoformat(),
        "config_path": str(config_path_obj),
        "storage_data_dir": str(storage_path),
        "snapshot": _snapshot_summary(snapshot),
        "keyword": _selection_summary(keyword_selection),
        "semantic": _semantic_summary(semantic_payload),
        "llm": _llm_summary(llm_payload),
        "ai": _selection_summary(
            ai_selection,
            skipped=ai_selection is None,
            reason=ai_skip_reason,
        ),
    }

    _write_review_text(
        outbox_path / "stage4_snapshot.json",
        json.dumps(
            {"summary": summary, "snapshot": asdict(snapshot)},
            ensure_ascii=False,
            indent=2,
        ),
    )
    _write_review_text(
        outbox_path / "stage4_selection_keyword.json",
        json.dumps(
            {"summary": summary, "selection": asdict(keyword_selection)},
            ensure_ascii=False,
            indent=2,
        ),
    )
    _write_review_text(
        outbox_path / "stage4_selection_semantic.json",
        json.dumps(
            {
                "summary": summary,
                "semantic": semantic_payload,
            },
            ensure_ascii=False,
            indent=2,
        ),
    )
    _write_review_text(
        outbox_path / "stage4_selection_ai.json",
        json.dumps(
            {
                "summary": summary,
                "selection": asdict(ai_selection) if ai_selection is not None else None,
                "skipped": ai_selection is None,
                "reason": ai_skip_reason,
            },
            ensure_ascii=False,
            indent=2,
        ),
    )
    _write_review_text(
        outbox_path / "stage4_selection_llm.json",
        json.dumps(
            {
                "summary": summary,
                "llm": llm_payload,
            },
            ensure_ascii=False,
            indent=2,
        ),
    )
    _write_review_text(
        outbox_path / "stage4_selection_review.md",
        _build_selection_review_markdown(
            generated_at=generated_at,
            config_path=config_path_obj,
            storage_data_dir=storage_path,
            snapshot=snapshot,
            keyword_selection=keyword_selection,
            ai_selection=ai_selection,
            ai_skip_reason=ai_skip_reason,
            semantic_payload=semantic_payload,
            llm_payload=llm_payload,
        ),
    )
    _write_review_text(outbox_path / "stage4_selection_run.log", run_log)
    return summary


def run_selection_review(
    *,
    config_path: str | Path = "config/config.yaml",
    outbox_dir: str | Path = "outbox",
    storage_data_dir: str | Path | None = None,
    mode: str = "current",
    frequency_file: str | None = None,
    interests_file: str | None = None,
) -> dict[str, object]:
    log_buffer = StringIO()
    resolved_config_path = Path(config_path).resolve()
    outbox_path = Path(outbox_dir)
    resolved_storage_dir = Path(storage_data_dir) if storage_data_dir else outbox_path / "stage4_storage"

    with redirect_stdout(log_buffer), redirect_stderr(log_buffer):
        config = load_config(str(resolved_config_path))
        timezone_name = config.get("TIMEZONE", DEFAULT_TIMEZONE)
        review_config = copy.deepcopy(config)
        review_config.setdefault("STORAGE", {})
        review_config["STORAGE"]["BACKEND"] = "local"
        review_config["STORAGE"]["FORMATS"] = {"TXT": False, "HTML": False}
        review_config.setdefault("STORAGE", {}).setdefault("LOCAL", {})
        review_config["STORAGE"]["LOCAL"]["DATA_DIR"] = str(resolved_storage_dir)
        review_config["STORAGE"]["LOCAL"]["RETENTION_DAYS"] = 0

        ctx = AppContext(review_config)
        ai_selection: SelectionResult | None = None
        ai_skip_reason = ""
        try:
            source_specs = _build_source_specs(config["PLATFORMS"])
            request_interval_ms = int(config["REQUEST_INTERVAL"])
            proxy_url = config["DEFAULT_PROXY"] if config.get("USE_PROXY") else None

            crawl_batch = DataFetcher(proxy_url=proxy_url).crawl(
                source_specs,
                request_interval=request_interval_ms,
            )
            generated_at = datetime.now(ZoneInfo(timezone_name))
            crawl_time = generated_at.strftime("%Y-%m-%d %H:%M:%S")
            crawl_date = generated_at.date().isoformat()
            normalized_batch = normalize_crawl_batch(
                crawl_batch=crawl_batch,
                crawl_time=crawl_time,
                crawl_date=crawl_date,
            )

            storage = ctx.get_storage_manager()
            save_success = storage.save_normalized_crawl_batch(normalized_batch)
            if not save_success:
                raise RuntimeError("failed to save normalized crawl batch")

            snapshot_service = ctx.create_snapshot_service()
            selection_service = ctx.create_selection_service()
            snapshot = snapshot_service.build(SnapshotOptions(mode=mode))
            keyword_selection = selection_service.run(
                snapshot,
                ctx.build_selection_options(
                    strategy="keyword",
                    frequency_file=frequency_file,
                    interests_file=interests_file,
                ),
            )

            ai_options = ctx.build_selection_options(
                strategy="ai",
                frequency_file=frequency_file,
                interests_file=interests_file,
            )
            api_key = str(ctx.ai_filter_model_config.get("API_KEY", "") or "").strip()
            if not api_key:
                ai_skip_reason = "AI filter runtime API_KEY is empty"
            else:
                try:
                    ai_selection = selection_service.run(snapshot, ai_options)
                except Exception as exc:
                    ai_skip_reason = f"{type(exc).__name__}: {exc}"
        finally:
            ctx.cleanup()

    return export_selection_outbox(
        outbox_dir=outbox_dir,
        generated_at=generated_at,
        config_path=resolved_config_path,
        storage_data_dir=resolved_storage_dir,
        snapshot=snapshot,
        keyword_selection=keyword_selection,
        ai_selection=ai_selection,
        ai_skip_reason=ai_skip_reason,
        run_log=log_buffer.getvalue(),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run crawl -> snapshot -> selection validation and export stage-4 artifacts.",
    )
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--outbox", default="outbox")
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--mode", default="current")
    parser.add_argument("--frequency-file", default=None)
    parser.add_argument("--interests-file", default=None)
    args = parser.parse_args(list(argv) if argv is not None else None)

    summary = run_selection_review(
        config_path=args.config,
        outbox_dir=args.outbox,
        storage_data_dir=args.data_dir,
        mode=args.mode,
        frequency_file=args.frequency_file,
        interests_file=args.interests_file,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
