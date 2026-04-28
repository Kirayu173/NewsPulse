# coding=utf-8
"""Explicit workflow-stage helpers built on runtime settings and container."""

from __future__ import annotations

from typing import Any

from newspulse.core.scheduler import ResolvedSchedule
from newspulse.runtime.container import RuntimeContainer
from newspulse.runtime.delivery_context import DeliveryOptionsBuilder
from newspulse.runtime.insight_context import InsightOptionsBuilder
from newspulse.runtime.render_context import RenderOptionsBuilder
from newspulse.runtime.selection_context import SelectionOptionsBuilder
from newspulse.runtime.settings import RuntimeSettings
from newspulse.workflow.shared.contracts import HotlistSnapshot, InsightResult, ReportPackage, SelectionResult
from newspulse.workflow.shared.options import SnapshotOptions


def run_selection_stage(
    settings: RuntimeSettings,
    container: RuntimeContainer,
    selection_builder: SelectionOptionsBuilder,
    *,
    mode: str,
    strategy: str | None = None,
    frequency_file: str | None = None,
    interests_file: str | None = None,
    snapshot_service=None,
    selection_service=None,
) -> tuple[HotlistSnapshot, SelectionResult]:
    snapshot_runner = snapshot_service or container.snapshot_service()
    selection_runner = selection_service or container.selection_service()
    snapshot = snapshot_runner.build(SnapshotOptions(mode=mode))
    options = selection_builder.build(
        strategy=strategy,
        frequency_file=frequency_file,
        interests_file=interests_file,
    )
    selection = selection_runner.run(snapshot, options)
    return snapshot, selection


def run_insight_stage(
    settings: RuntimeSettings,
    container: RuntimeContainer,
    selection_builder: SelectionOptionsBuilder,
    insight_builder: InsightOptionsBuilder,
    *,
    report_mode: str,
    snapshot: HotlistSnapshot | None = None,
    selection: SelectionResult | None = None,
    strategy: str | None = None,
    frequency_file: str | None = None,
    interests_file: str | None = None,
    schedule: ResolvedSchedule | None = None,
    snapshot_service=None,
    selection_service=None,
    insight_service=None,
) -> InsightResult:
    options = insight_builder.build(report_mode=report_mode)
    if not options.enabled or options.strategy == "noop":
        return _build_noop_insight_result("insight stage disabled", report_mode=report_mode, schedule=schedule)

    if schedule is not None:
        if not schedule.analyze:
            return _build_noop_insight_result(
                "insight stage disabled by schedule",
                report_mode=report_mode,
                schedule=schedule,
            )

        if schedule.once_analyze and schedule.period_key:
            date_str = settings.format_date()
            if container.storage().has_period_executed(date_str, schedule.period_key, "analyze"):
                return _build_noop_insight_result(
                    f"insight stage already executed for {schedule.period_name or schedule.period_key}",
                    report_mode=report_mode,
                    schedule=schedule,
                )

    if snapshot is None or selection is None:
        snapshot, selection = run_selection_stage(
            settings,
            container,
            selection_builder,
            mode=options.mode,
            strategy=settings.selection.strategy if strategy is None else strategy,
            frequency_file=frequency_file,
            interests_file=interests_file,
            snapshot_service=snapshot_service,
            selection_service=selection_service,
        )

    runner = insight_service or container.insight_service()
    insight = runner.run(snapshot, selection, options)

    if _is_successful_insight_result(insight) and schedule is not None and schedule.once_analyze and schedule.period_key:
        container.storage().record_period_execution(settings.format_date(), schedule.period_key, "analyze")

    return insight


def assemble_report_package(
    container: RuntimeContainer,
    snapshot: HotlistSnapshot,
    selection: SelectionResult,
    insight: InsightResult,
    *,
    report_assembler=None,
) -> ReportPackage:
    assembler = report_assembler or container.report_assembler()
    return assembler.assemble(snapshot, selection, insight)


def run_render_stage(
    container: RuntimeContainer,
    render_builder: RenderOptionsBuilder,
    report: ReportPackage,
    *,
    emit_html: bool | None = None,
    emit_notification: bool | None = None,
    display_regions: list[str] | None = None,
    update_info: dict[str, Any] | None = None,
    render_service=None,
):
    options = render_builder.build(
        emit_html=emit_html,
        emit_notification=emit_notification,
        display_regions=display_regions,
        update_info=update_info,
    )
    service = render_service or container.render_service()
    return service.run(report, options)


def run_delivery_stage(
    container: RuntimeContainer,
    delivery_builder: DeliveryOptionsBuilder,
    payloads,
    *,
    enabled: bool | None = None,
    channels: list[str] | None = None,
    dry_run: bool = False,
    proxy_url: str | None = None,
    delivery_service=None,
):
    options = delivery_builder.build(
        enabled=enabled,
        channels=channels,
        dry_run=dry_run,
        proxy_url=proxy_url,
    )
    service = delivery_service or container.delivery_service()
    return service.run(payloads, options)


def _build_noop_insight_result(
    reason: str,
    *,
    report_mode: str,
    schedule: ResolvedSchedule | None = None,
) -> InsightResult:
    diagnostics = {
        "report_mode": report_mode,
        "generation_status": "skipped",
        "skipped": True,
        "reason": reason,
    }
    if schedule is not None:
        diagnostics["schedule_analyze"] = schedule.analyze
        diagnostics["schedule_period"] = schedule.period_key
    return InsightResult(
        enabled=False,
        strategy="noop",
        generation_status="skipped",
        diagnostics=diagnostics,
    )


def _is_successful_insight_result(insight: InsightResult) -> bool:
    diagnostics = dict(insight.diagnostics or {})
    return (
        insight.enabled
        and bool(insight.sections)
        and insight.generation_status in {"ok", "partial", "fallback"}
        and not bool(diagnostics.get("skipped"))
        and not bool(diagnostics.get("error"))
        and not bool(diagnostics.get("parse_error"))
    )
