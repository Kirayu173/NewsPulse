# coding=utf-8
"""Render stage package."""

from newspulse.workflow.render.html import HTMLRenderAdapter
from newspulse.workflow.render.html_sections import render_hotlist_stats_html
from newspulse.workflow.render.models import (
    DEFAULT_RENDER_REGIONS,
    HTMLArtifact,
    RenderArtifacts,
    RenderViewModel,
    build_render_view_model,
)
from newspulse.workflow.render.notification_content import DEFAULT_BATCH_SIZES, split_content_into_batches
from newspulse.workflow.render.notification import NotificationRenderAdapter
from newspulse.workflow.render.service import RenderService

__all__ = [
    "DEFAULT_BATCH_SIZES",
    "DEFAULT_RENDER_REGIONS",
    "HTMLArtifact",
    "HTMLRenderAdapter",
    "NotificationRenderAdapter",
    "RenderArtifacts",
    "RenderViewModel",
    "RenderService",
    "build_render_view_model",
    "render_hotlist_stats_html",
    "split_content_into_batches",
]
