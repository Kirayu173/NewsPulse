# coding=utf-8
"""Runtime settings, container, and workflow helpers."""

from newspulse.runtime.bootstrap import ApplicationRuntime, build_runtime
from newspulse.runtime.container import RuntimeContainer, RuntimeProviders
from newspulse.runtime.delivery_context import DeliveryOptionsBuilder
from newspulse.runtime.insight_context import InsightOptionsBuilder
from newspulse.runtime.render_context import RenderOptionsBuilder
from newspulse.runtime.selection_context import SelectionOptionsBuilder
from newspulse.runtime.settings import RuntimeSettings
from newspulse.runtime.workflow import (
    assemble_report_package,
    run_delivery_stage,
    run_insight_stage,
    run_render_stage,
    run_selection_stage,
)

__all__ = [
    "ApplicationRuntime",
    "RuntimeContainer",
    "RuntimeProviders",
    "RuntimeSettings",
    "SelectionOptionsBuilder",
    "InsightOptionsBuilder",
    "RenderOptionsBuilder",
    "DeliveryOptionsBuilder",
    "build_runtime",
    "run_selection_stage",
    "run_insight_stage",
    "assemble_report_package",
    "run_render_stage",
    "run_delivery_stage",
]
