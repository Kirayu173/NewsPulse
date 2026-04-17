# coding=utf-8
"""Render stage package."""

from newspulse.workflow.render.assembler import HotlistReportAssembler
from newspulse.workflow.render.html import HTMLRenderAdapter
from newspulse.workflow.render.models import (
    DEFAULT_RENDER_REGIONS,
    HTMLArtifact,
    REPORT_TYPE_BY_MODE,
    RenderArtifacts,
    RenderReportMeta,
    RenderViewModel,
    build_render_view_model,
)
from newspulse.workflow.render.notification import NotificationRenderAdapter
from newspulse.workflow.render.service import RenderService

__all__ = [
    "DEFAULT_RENDER_REGIONS",
    "HTMLArtifact",
    "HTMLRenderAdapter",
    "HotlistReportAssembler",
    "NotificationRenderAdapter",
    "REPORT_TYPE_BY_MODE",
    "RenderArtifacts",
    "RenderReportMeta",
    "RenderViewModel",
    "RenderService",
    "build_render_view_model",
]
