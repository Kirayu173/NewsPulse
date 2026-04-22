# coding=utf-8
"""Stage-5 review exporter for the native insight workflow."""

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

from newspulse.context import AppContext
from newspulse.core import load_config
from newspulse.crawler.fetcher import DataFetcher
from newspulse.crawler.models import CrawlSourceSpec
from newspulse.storage import normalize_crawl_batch
from newspulse.utils.time import DEFAULT_TIMEZONE
from newspulse.workflow.shared.options import SnapshotOptions
from newspulse.workflow.shared.review_helpers import (
    REVIEW_FILE_ENCODING,
    build_source_specs as _build_source_specs,
    write_review_text as _write_review_text,
)

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
    outbox_path = Path(outbox_dir)
    outbox_path.mkdir(parents=True, exist_ok=True)
    config_path_obj = Path(config_path)
    storage_path = Path(storage_data_dir)
    diagnostics = dict(getattr(insight, 'diagnostics', {}) or {})

    summary = {
        'generated_at': generated_at.isoformat(),
        'config_path': str(config_path_obj),
        'storage_data_dir': str(storage_path),
        'snapshot': {
            'mode': snapshot.mode,
            'generated_at': snapshot.generated_at,
            'item_count': len(snapshot.items),
            'new_item_count': len(snapshot.new_items),
            'failed_source_count': len(snapshot.failed_sources),
        },
        'selection': {
            'strategy': selection.strategy,
            'total_candidates': selection.total_candidates,
            'total_selected': selection.total_selected,
        },
        'insight': {
            'enabled': bool(insight.enabled),
            'strategy': str(insight.strategy or ''),
            'section_count': len(insight.sections),
            'item_analysis_count': len(insight.item_analyses),
            'error_count': int(diagnostics.get('error_count', 0) or 0),
        },
    }

    _write_review_text(
        outbox_path / 'stage5_insight_input.json',
        json.dumps(
            {
                'summary': summary,
                'input_contexts': diagnostics.get('input_contexts', []),
            },
            ensure_ascii=False,
            indent=2,
        ),
    )
    _write_review_text(
        outbox_path / 'stage5_content_fetch.json',
        json.dumps(
            {
                'summary': summary,
                'content_payloads': diagnostics.get('content_payloads', []),
            },
            ensure_ascii=False,
            indent=2,
        ),
    )
    _write_review_text(
        outbox_path / 'stage5_content_reduce.json',
        json.dumps(
            {
                'summary': summary,
                'reduced_bundles': diagnostics.get('reduced_bundles', []),
            },
            ensure_ascii=False,
            indent=2,
        ),
    )
    _write_review_text(
        outbox_path / 'stage5_item_analysis.json',
        json.dumps(
            {
                'summary': summary,
                'item_analyses': diagnostics.get('item_analysis_payloads', []),
            },
            ensure_ascii=False,
            indent=2,
        ),
    )
    _write_review_text(
        outbox_path / 'stage5_insight.json',
        json.dumps(
            {
                'summary': summary,
                'insight': asdict(insight),
            },
            ensure_ascii=False,
            indent=2,
        ),
    )
    _write_review_text(
        outbox_path / 'stage5_insight_review.md',
        _build_insight_review_markdown(
            generated_at=generated_at,
            config_path=config_path_obj,
            storage_data_dir=storage_path,
            snapshot=snapshot,
            selection=selection,
            insight=insight,
        ),
    )
    _write_review_text(outbox_path / 'stage5_insight_run.log', run_log)
    return summary


def _build_insight_review_markdown(
    *,
    generated_at: datetime,
    config_path: Path,
    storage_data_dir: Path,
    snapshot: Any,
    selection: Any,
    insight: Any,
) -> str:
    diagnostics = dict(getattr(insight, 'diagnostics', {}) or {})
    input_contexts = list(diagnostics.get('input_contexts', []))
    content_payloads = list(diagnostics.get('content_payloads', []))
    reduced_bundles = list(diagnostics.get('reduced_bundles', []))
    item_analyses = list(diagnostics.get('item_analysis_payloads', []))
    aggregate = dict(diagnostics.get('aggregate', {}) or {})

    lines: list[str] = []
    lines.append('# Stage 5 Insight Review')
    lines.append('')
    lines.append(f'- generated_at: {generated_at.strftime("%Y-%m-%d %H:%M:%S %z")}')
    lines.append(f'- config_path: `{config_path}`')
    lines.append(f'- storage_data_dir: `{storage_data_dir}`')
    lines.append(f'- snapshot_items: {len(snapshot.items)}')
    lines.append(f'- selected_items: {selection.total_selected}')
    lines.append(f'- item_analyses: {len(insight.item_analyses)}')
    lines.append(f'- sections: {len(insight.sections)}')
    if diagnostics.get('error'):
        lines.append(f'- error: {diagnostics.get("error")}')
    lines.append('')

    lines.append('## Insight Inputs')
    lines.append('')
    for index, row in enumerate(input_contexts[:12], start=1):
        source_name = row.get('source_name', '')
        title = row.get('title', '')
        summary = row.get('source_context', {}).get('summary', '') if isinstance(row.get('source_context'), dict) else ''
        matched_topics = row.get('selection_evidence', {}).get('matched_topics', []) if isinstance(row.get('selection_evidence'), dict) else []
        lines.append(f'{index}. [{source_name}] {title}')
        if summary:
            lines.append(f'   summary: {summary}')
        if matched_topics:
            lines.append(f'   matched_topics: {", ".join(matched_topics)}')
    if len(input_contexts) > 12:
        lines.append(f'... ({len(input_contexts) - 12} more inputs)')
    lines.append('')

    lines.append('## Content Fetch')
    lines.append('')
    for index, row in enumerate(content_payloads[:12], start=1):
        lines.append(
            f"{index}. [{row.get('source_type', '')}] {row.get('title', '')} -> {row.get('status', '')} / {row.get('extractor_name', '')}"
        )
        excerpt = str(row.get('excerpt', '') or '').strip()
        if excerpt:
            lines.append(f'   excerpt: {excerpt[:180]}')
        error_message = str(row.get('error_message', '') or '').strip()
        if error_message:
            lines.append(f'   error: {error_message}')
    if len(content_payloads) > 12:
        lines.append(f'... ({len(content_payloads) - 12} more fetch payloads)')
    lines.append('')

    lines.append('## Reduced Content')
    lines.append('')
    for index, row in enumerate(reduced_bundles[:12], start=1):
        diagnostics_row = row.get('diagnostics', {}) if isinstance(row.get('diagnostics'), dict) else {}
        lines.append(
            f"{index}. {row.get('news_item_id', '')} -> {row.get('reducer_name', '')} / budget={diagnostics_row.get('budget_used', 0)}"
        )
        reduced_text = str(row.get('reduced_text', '') or '').strip()
        if reduced_text:
            preview = reduced_text[:240] + ('...' if len(reduced_text) > 240 else '')
            lines.append(f'   reduced_text: {preview}')
    if len(reduced_bundles) > 12:
        lines.append(f'... ({len(reduced_bundles) - 12} more reduced bundles)')
    lines.append('')

    lines.append('## Item Analyses')
    lines.append('')
    for index, row in enumerate(item_analyses[:12], start=1):
        lines.append(f"{index}. {row.get('title', '')}")
        if row.get('what_happened'):
            lines.append(f"   what_happened: {row.get('what_happened')}")
        if row.get('why_it_matters'):
            lines.append(f"   why_it_matters: {row.get('why_it_matters')}")
        evidence = row.get('evidence', [])
        if isinstance(evidence, list) and evidence:
            lines.append(f"   evidence: {' | '.join(str(item) for item in evidence[:3])}")
        diagnostics_row = row.get('diagnostics', {}) if isinstance(row.get('diagnostics'), dict) else {}
        if diagnostics_row.get('error'):
            lines.append(f"   error: {diagnostics_row.get('error')}")
    if len(item_analyses) > 12:
        lines.append(f'... ({len(item_analyses) - 12} more item analyses)')
    lines.append('')

    lines.append('## Aggregate Insight')
    lines.append('')
    lines.append(f"- aggregate_item_count: {aggregate.get('item_count', 0)}")
    lines.append(f"- aggregate_section_count: {aggregate.get('section_count', len(insight.sections))}")
    if aggregate.get('error'):
        lines.append(f"- aggregate_error: {aggregate.get('error')}")
    lines.append('')
    for section in insight.sections:
        lines.append(f"### {section.title} ({section.key})")
        lines.append('')
        lines.append(section.content)
        lines.append('')
        metadata = dict(section.metadata or {})
        supporting_news_ids = metadata.get('supporting_news_ids', [])
        if supporting_news_ids:
            lines.append(f"- supporting_news_ids: {', '.join(str(item) for item in supporting_news_ids)}")
        supporting_topics = metadata.get('supporting_topics', [])
        if supporting_topics:
            lines.append(f"- supporting_topics: {', '.join(str(item) for item in supporting_topics)}")
        lines.append('')

    return '\n'.join(lines)


def run_insight_review(
    *,
    config_path: str | Path = 'config/config.yaml',
    outbox_dir: str | Path = 'outbox',
    storage_data_dir: str | Path | None = None,
    mode: str = 'current',
    frequency_file: str | None = None,
    interests_file: str | None = None,
) -> dict[str, Any]:
    log_buffer = StringIO()
    resolved_config_path = Path(config_path).resolve()
    outbox_path = Path(outbox_dir)
    resolved_storage_dir = Path(storage_data_dir) if storage_data_dir else outbox_path / 'stage5_storage'

    with redirect_stdout(log_buffer), redirect_stderr(log_buffer):
        config = load_config(str(resolved_config_path))
        timezone_name = config.get('TIMEZONE', DEFAULT_TIMEZONE)
        review_config = copy.deepcopy(config)
        review_config.setdefault('STORAGE', {})
        review_config['STORAGE']['BACKEND'] = 'local'
        review_config['STORAGE']['FORMATS'] = {'TXT': False, 'HTML': False}
        review_config.setdefault('STORAGE', {}).setdefault('LOCAL', {})
        review_config['STORAGE']['LOCAL']['DATA_DIR'] = str(resolved_storage_dir)
        review_config['STORAGE']['LOCAL']['RETENTION_DAYS'] = 0

        ctx = AppContext(review_config)
        try:
            source_specs = _build_source_specs(config['PLATFORMS'])
            request_interval_ms = int(config['REQUEST_INTERVAL'])
            proxy_url = config['DEFAULT_PROXY'] if config.get('USE_PROXY') else None

            crawl_batch = DataFetcher(proxy_url=proxy_url).crawl(
                source_specs,
                request_interval=request_interval_ms,
            )
            generated_at = datetime.now(ZoneInfo(timezone_name))
            crawl_time = generated_at.strftime('%Y-%m-%d %H:%M:%S')
            crawl_date = generated_at.date().isoformat()
            normalized_batch = normalize_crawl_batch(
                crawl_batch=crawl_batch,
                crawl_time=crawl_time,
                crawl_date=crawl_date,
            )

            storage = ctx.get_storage_manager()
            save_success = storage.save_normalized_crawl_batch(normalized_batch)
            if not save_success:
                raise RuntimeError('failed to save normalized crawl batch')

            snapshot_service = ctx.create_snapshot_service()
            selection_service = ctx.create_selection_service()
            snapshot = snapshot_service.build(SnapshotOptions(mode=mode))
            selection = selection_service.run(
                snapshot,
                ctx.build_selection_options(
                    strategy=ctx.filter_method,
                    frequency_file=frequency_file,
                    interests_file=interests_file,
                ),
            )
            insight = ctx.run_insight_stage(
                report_mode=mode,
                snapshot=snapshot,
                selection=selection,
                strategy=ctx.filter_method,
                frequency_file=frequency_file,
                interests_file=interests_file,
            )
        finally:
            ctx.cleanup()

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
        description='Run crawl -> snapshot -> selection -> insight validation and export stage-5 artifacts.',
    )
    parser.add_argument('--config', default='config/config.yaml')
    parser.add_argument('--outbox', default='outbox')
    parser.add_argument('--data-dir', default=None)
    parser.add_argument('--mode', default='current')
    parser.add_argument('--frequency-file', default=None)
    parser.add_argument('--interests-file', default=None)
    args = parser.parse_args(list(argv) if argv is not None else None)

    summary = run_insight_review(
        config_path=args.config,
        outbox_dir=args.outbox,
        storage_data_dir=args.data_dir,
        mode=args.mode,
        frequency_file=args.frequency_file,
        interests_file=args.interests_file,
    )
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
