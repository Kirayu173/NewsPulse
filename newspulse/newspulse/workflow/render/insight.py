# coding=utf-8
"""Insight render helpers shared by HTML and notification rendering."""

from __future__ import annotations

import re

from newspulse.report.helpers import html_escape
from newspulse.workflow.render.models import RenderInsightView


def _format_list_content(text: str) -> str:
    if not text:
        return ""

    normalized = text.strip().replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"(?<!\n)(\d+\.)\s*", r"\n\1 ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.lstrip("\n")


def _iter_sections(insight: RenderInsightView):
    for section in insight.sections:
        content = _format_list_content(section.content)
        if not content:
            continue
        yield section.title or section.key, content


def render_insight_markdown(insight: RenderInsightView) -> str:
    """Render insight blocks for markdown-based notification channels."""

    if not insight.visible:
        return ""

    if insight.status == "skipped":
        return f"跳过: {insight.message or '本次未生成 AI 分析'}"
    if insight.status == "error":
        return f"AI 分析失败: {insight.message or '未知错误'}"

    lines = ["**AI 分析**", ""]
    for title, content in _iter_sections(insight):
        lines.extend([f"**{title}**", content, ""])
    return "\n".join(lines).strip()


def render_insight_html_rich(insight: RenderInsightView) -> str:
    """Render insight blocks for the HTML report."""

    if not insight.visible:
        return ""

    if insight.status in {"skipped", "error"} and not insight.sections:
        css_class = "ai-info" if insight.status == "skipped" else "ai-error"
        prefix = "跳过" if insight.status == "skipped" else "错误"
        return (
            '<div class="ai-section">'
            f'<div class="{css_class}">{prefix} {html_escape(insight.message or "")}</div>'
            "</div>"
        )

    parts = [
        '<div class="ai-section">',
        '  <div class="ai-section-header">',
        '    <div class="ai-section-title">AI 分析</div>',
        '    <span class="ai-section-badge">AI</span>',
        '  </div>',
        '  <div class="ai-blocks-grid">',
    ]

    for title, content in _iter_sections(insight):
        content_html = html_escape(content).replace("\n", "<br>")
        parts.extend(
            [
                '    <div class="ai-block">',
                f'      <div class="ai-block-title">{html_escape(title)}</div>',
                f'      <div class="ai-block-content">{content_html}</div>',
                '    </div>',
            ]
        )

    parts.extend(["  </div>", "</div>"])
    return "\n".join(parts)


__all__ = ["render_insight_html_rich", "render_insight_markdown"]
