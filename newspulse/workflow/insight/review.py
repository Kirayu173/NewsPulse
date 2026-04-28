# coding=utf-8
"""Stage-5 review exporter for the lightweight insight workflow."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any, Sequence
from zoneinfo import ZoneInfo

from newspulse.core import load_config
from newspulse.crawler.fetcher import DataFetcher
from newspulse.runtime import build_runtime, run_insight_stage
from newspulse.storage import normalize_crawl_batch
from newspulse.utils.time import DEFAULT_TIMEZONE
from newspulse.workflow.shared.options import SnapshotOptions
from newspulse.workflow.shared.review_helpers import ReviewOutboxWriter as _ReviewOutboxWriter


def export_insight_outbox(
    *,
    outbox_dir: str | Path,
    generated_at: datetime,
    config_path: str | Path,
    storage_data_dir: str | Path,
    snapshot: Any,
    selection: Any,
    insight: Any,
    run_log: str,
) -> dict[str, Any]:
    outbox = _ReviewOutboxWriter(outbox_dir)
    config_path_obj = Path(config_path)
    storage_path = Path(storage_data_dir)
    diagnostics = dict(getattr(insight, "diagnostics", {}) or {})

    summary = {
        "generated_at": generated_at.isoformat(),
        "config_path": str(config_path_obj),
        "storage_data_dir": str(storage_path),
        "snapshot": {
            "mode": snapshot.mode,
            "generated_at": snapshot.generated_at,
            "item_count": len(snapshot.items),
            "new_item_count": len(snapshot.new_items),
            "failed_source_count": len(snapshot.failed_sources),
        },
        "selection": {
            "strategy": selection.strategy,
            "total_candidates": selection.total_candidates,
            "total_selected": selection.total_selected,
        },
        "insight": {
            "enabled": bool(insight.enabled),
            "strategy": str(insight.strategy or ""),
            "generation_status": str(getattr(insight, "generation_status", "") or diagnostics.get("generation_status", "")),
            "section_count": len(insight.sections),
            "summary_count": len(insight.summaries),
            "item_summary_count": len([summary for summary in insight.summaries if summary.kind == "item"]),
            "item_summary_failed_count": int(diagnostics.get("item_summary_failed_count", 0) or 0),
            "report_summary_present": bool(diagnostics.get("report_summary_present", False)),
        },
    }

    outbox.write_stage_json(
        "stage5_summary_input.json",
        summary=summary,
        input_contexts=diagnostics.get("input_contexts", []),
    )
    outbox.write_stage_json(
        "stage5_summaries.json",
        summary=summary,
        summaries=diagnostics.get("summary_payloads", []),
        item_summaries=diagnostics.get("item_summary_payloads", []),
        report_summary=diagnostics.get("report_summary_payload", {}),
        content_fetch=diagnostics.get("content_fetch", {}),
        content_reduction=diagnostics.get("content_reduction", {}),
        summary_generation=diagnostics.get("summary_generation", {}),
    )
    outbox.write_stage_json(
        "stage5_global_insight.json",
        summary=summary,
        insight=asdict(insight),
    )
    outbox.write_markdown(
        "stage5_summary_review.md",
        _build_summary_review_markdown(
            generated_at=generated_at,
            config_path=config_path_obj,
            storage_data_dir=storage_path,
            snapshot=snapshot,
            selection=selection,
            insight=insight,
        ),
    )
    outbox.write_markdown(
        "stage5_global_insight_review.md",
        _build_global_insight_review_markdown(
            generated_at=generated_at,
            config_path=config_path_obj,
            storage_data_dir=storage_path,
            snapshot=snapshot,
            selection=selection,
            insight=insight,
        ),
    )
    outbox.write_log("stage5_summary_global_insight_run.log", run_log)
    return summary


def _build_summary_review_markdown(
    *,
    generated_at: datetime,
    config_path: Path,
    storage_data_dir: Path,
    snapshot: Any,
    selection: Any,
    insight: Any,
) -> str:
    diagnostics = dict(getattr(insight, "diagnostics", {}) or {})
    input_contexts = list(diagnostics.get("input_contexts", []))
    reduced_contexts = list(diagnostics.get("reduced_contexts", []))
    item_summaries = list(diagnostics.get("item_summary_payloads", []))
    report_summary = dict(diagnostics.get("report_summary_payload", {}) or {})

    lines: list[str] = []
    lines.append("# Stage 5 Summary Review")
    lines.append("")
    lines.append(f'- generated_at: {generated_at.strftime("%Y-%m-%d %H:%M:%S %z") }')
    lines.append(f'- config_path: `{config_path}`')
    lines.append(f'- storage_data_dir: `{storage_data_dir}`')
    lines.append(f'- snapshot_items: {len(snapshot.items)}')
    lines.append(f'- selected_items: {selection.total_selected}')
    lines.append(f'- summaries: {len(insight.summaries)}')
    lines.append(f'- item_summaries: {len(item_summaries)}')
    lines.append(f'- item_summary_failed_count: {diagnostics.get("item_summary_failed_count", 0)}')
    lines.append(f'- report_summary_present: {bool(report_summary)}')
    lines.append(f'- content_fetch_enabled: {diagnostics.get("content_fetch_enabled", False)}')
    lines.append(f'- content_fetch_success_count: {diagnostics.get("content_fetch_success_count", 0)}')
    lines.append(f'- content_fetch_failed_count: {diagnostics.get("content_fetch_failed_count", 0)}')
    lines.append(f'- content_reduced_max_chars: {diagnostics.get("content_reduced_max_chars", 0)}')
    if diagnostics.get("reason"):
        lines.append(f'- reason: {diagnostics.get("reason")}')
    if diagnostics.get("error"):
        lines.append(f'- error: {diagnostics.get("error")}')
    lines.append("")

    lines.append("## Summary Inputs")
    lines.append("")
    for index, row in enumerate(input_contexts[:12], start=1):
        source_name = row.get("source_name", "")
        title = row.get("title", "")
        source_context = row.get("source_context", {}) if isinstance(row.get("source_context"), dict) else {}
        evidence = row.get("selection_evidence", {}) if isinstance(row.get("selection_evidence"), dict) else {}
        lines.append(f"{index}. [{source_name}] {title}")
        if source_context.get("summary"):
            lines.append(f"   summary: {source_context.get('summary')}")
        attributes = source_context.get("attributes", [])
        if isinstance(attributes, list) and attributes:
            lines.append(f"   attributes: {', '.join(str(item) for item in attributes[:4])}")
        matched_topics = evidence.get("matched_topics", [])
        if isinstance(matched_topics, list) and matched_topics:
            lines.append(f"   matched_topics: {', '.join(str(item) for item in matched_topics[:4])}")
        llm_reasons = evidence.get("llm_reasons", [])
        if isinstance(llm_reasons, list) and llm_reasons:
            lines.append(f"   llm_reasons: {' | '.join(str(item) for item in llm_reasons[:3])}")
    if len(input_contexts) > 12:
        lines.append(f"... ({len(input_contexts) - 12} more inputs)")
    lines.append("")

    lines.append("## Reduced Contexts")
    lines.append("")
    for index, row in enumerate(reduced_contexts[:12], start=1):
        lines.append(f"{index}. {row.get('title', '')}")
        diagnostics_row = row.get("diagnostics", {}) if isinstance(row.get("diagnostics"), dict) else {}
        lines.append(f"   reduced_chars: {diagnostics_row.get('reduced_chars', 0)}")
        lines.append(f"   fetch_status: {diagnostics_row.get('fetch_status', '')}")
        paragraphs = row.get("key_paragraphs", [])
        if isinstance(paragraphs, list) and paragraphs:
            lines.append(f"   first_paragraph: {str(paragraphs[0])[:180]}")
    if len(reduced_contexts) > 12:
        lines.append(f"... ({len(reduced_contexts) - 12} more reduced contexts)")
    lines.append("")

    lines.append("## Report Summary")
    lines.append("")
    if report_summary:
        lines.append(report_summary.get("summary", ""))
        if report_summary.get("evidence_topics"):
            lines.append(f"- evidence_topics: {', '.join(str(item) for item in report_summary.get('evidence_topics', [])[:8])}")
    else:
        lines.append("No report summary was generated.")
    lines.append("")

    lines.append("## Item Summaries")
    lines.append("")
    for index, row in enumerate(item_summaries[:12], start=1):
        lines.append(f"{index}. {row.get('title', '')}")
        if row.get("summary"):
            lines.append(f"   summary: {row.get('summary')}")
        if row.get("evidence_topics"):
            lines.append(f"   evidence_topics: {', '.join(str(item) for item in row.get('evidence_topics', [])[:4])}")
        if row.get("evidence_notes"):
            lines.append(f"   evidence_notes: {' | '.join(str(item) for item in row.get('evidence_notes', [])[:3])}")
    if len(item_summaries) > 12:
        lines.append(f"... ({len(item_summaries) - 12} more item summaries)")
    lines.append("")

    return "\n".join(lines)


def _build_global_insight_review_markdown(
    *,
    generated_at: datetime,
    config_path: Path,
    storage_data_dir: Path,
    snapshot: Any,
    selection: Any,
    insight: Any,
) -> str:
    diagnostics = dict(getattr(insight, "diagnostics", {}) or {})
    aggregate = dict(diagnostics.get("aggregate", {}) or {})

    lines: list[str] = []
    lines.append("# Stage 5 Global Insight Review")
    lines.append("")
    lines.append(f'- generated_at: {generated_at.strftime("%Y-%m-%d %H:%M:%S %z") }')
    lines.append(f'- config_path: `{config_path}`')
    lines.append(f'- storage_data_dir: `{storage_data_dir}`')
    lines.append(f'- snapshot_items: {len(snapshot.items)}')
    lines.append(f'- selected_items: {selection.total_selected}')
    lines.append(f'- summaries: {len(insight.summaries)}')
    lines.append(f'- sections: {len(insight.sections)}')
    if diagnostics.get("reason"):
        lines.append(f'- reason: {diagnostics.get("reason")}')
    if diagnostics.get("error"):
        lines.append(f'- error: {diagnostics.get("error")}')
    lines.append("")

    lines.append("## Aggregate Diagnostics")
    lines.append("")
    lines.append(f"- aggregate_summary_count: {aggregate.get('summary_count', len(insight.summaries))}")
    lines.append(f"- aggregate_item_summary_count: {aggregate.get('item_summary_count', 0)}")
    lines.append(f"- aggregate_section_count: {aggregate.get('section_count', len(insight.sections))}")
    if aggregate.get("source_distribution"):
        lines.append(f"- source_distribution: {json.dumps(aggregate.get('source_distribution'), ensure_ascii=False)}")
    if aggregate.get("topic_distribution"):
        lines.append(f"- topic_distribution: {json.dumps(aggregate.get('topic_distribution'), ensure_ascii=False)}")
    if aggregate.get("error"):
        lines.append(f"- aggregate_error: {aggregate.get('error')}")
    lines.append("")
    for section in insight.sections:
        lines.append(f"### {section.title} ({section.key})")
        lines.append("")
        lines.append(section.content)
        lines.append("")
        metadata = dict(section.metadata or {})
        supporting_news_ids = metadata.get("supporting_news_ids", [])
        if supporting_news_ids:
            lines.append(f"- supporting_news_ids: {', '.join(str(item) for item in supporting_news_ids)}")
        supporting_topics = metadata.get("supporting_topics", [])
        if supporting_topics:
            lines.append(f"- supporting_topics: {', '.join(str(item) for item in supporting_topics)}")
        lines.append("")

    return "\n".join(lines)


def run_insight_review(
    *,
    config_path: str | Path = "config/config.yaml",
    outbox_dir: str | Path = "outbox",
    storage_data_dir: str | Path | None = None,
    mode: str = "current",
    frequency_file: str | None = None,
    interests_file: str | None = None,
) -> dict[str, Any]:
    log_buffer = StringIO()
    resolved_config_path = Path(config_path).resolve()
    outbox_path = Path(outbox_dir)
    resolved_storage_dir = Path(storage_data_dir) if storage_data_dir else outbox_path / "stage5_storage"

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

        runtime = build_runtime(review_config)
        try:
            settings = runtime.settings
            source_specs = settings.crawler.crawl_source_specs
            request_interval_ms = settings.crawler.request_interval_ms
            proxy_url = settings.crawler.default_proxy_url if settings.crawler.proxy_enabled else None

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

            storage = runtime.container.storage()
            save_success = storage.save_normalized_crawl_batch(normalized_batch)
            if not save_success:
                raise RuntimeError("failed to save normalized crawl batch")

            snapshot_service = runtime.container.snapshot_service()
            selection_service = runtime.container.selection_service()
            snapshot = snapshot_service.build(SnapshotOptions(mode=mode))
            selection = selection_service.run(
                snapshot,
                runtime.selection_builder.build(
                    strategy=settings.selection.strategy,
                    frequency_file=frequency_file,
                    interests_file=interests_file,
                ),
            )
            insight = run_insight_stage(
                settings,
                runtime.container,
                runtime.selection_builder,
                runtime.insight_builder,
                report_mode=mode,
                snapshot=snapshot,
                selection=selection,
                strategy=settings.selection.strategy,
                frequency_file=frequency_file,
                interests_file=interests_file,
            )
        finally:
            runtime.cleanup()

    return export_insight_outbox(
        outbox_dir=outbox_dir,
        generated_at=generated_at,
        config_path=resolved_config_path,
        storage_data_dir=resolved_storage_dir,
        snapshot=snapshot,
        selection=selection,
        insight=insight,
        run_log=log_buffer.getvalue(),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run crawl -> snapshot -> selection -> insight validation and export stage-5 artifacts.",
    )
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--outbox", default="outbox")
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--mode", default="current")
    parser.add_argument("--frequency-file", default=None)
    parser.add_argument("--interests-file", default=None)
    args = parser.parse_args(list(argv) if argv is not None else None)

    summary = run_insight_review(
        config_path=args.config,
        outbox_dir=args.outbox,
        storage_data_dir=args.data_dir,
        mode=args.mode,
        frequency_file=args.frequency_file,
        interests_file=args.interests_file,
    )
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
