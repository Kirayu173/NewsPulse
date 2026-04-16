# coding=utf-8
"""Render AI analysis results for different notification channels."""

from __future__ import annotations

import html as html_lib
import re
from typing import Callable, Dict, Iterable, List, Tuple

from .analyzer import AIAnalysisResult


_SECTION_LABELS: List[Tuple[str, str]] = [
    ("core_trends", "核心趋势"),
    ("sentiment_controversy", "情绪与争议"),
    ("signals", "关键信号"),
    ("outlook_strategy", "后续判断"),
]


def _escape_html(text: str) -> str:
    return html_lib.escape(text or "")


def _format_list_content(text: str) -> str:
    if not text:
        return ""

    normalized = text.strip().replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"(?<!\n)(\d+\.)\s*", r"\n\1 ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.lstrip("\n")


def _format_standalone_summaries(summaries: Dict[str, str]) -> str:
    lines: List[str] = []
    for source_name, summary in summaries.items():
        if not summary:
            continue
        lines.append(f"[{source_name}]\n{summary.strip()}")
    return "\n\n".join(lines)


def _iter_sections(result: AIAnalysisResult) -> Iterable[Tuple[str, str]]:
    for attr_name, label in _SECTION_LABELS:
        value = getattr(result, attr_name, "")
        if value:
            yield label, _format_list_content(value)

    if result.standalone_summaries:
        summaries_text = _format_standalone_summaries(result.standalone_summaries)
        if summaries_text:
            yield "独立热榜摘要", summaries_text


def render_ai_analysis_markdown(result: AIAnalysisResult) -> str:
    if not result.success:
        if result.skipped:
            return f"跳过: {result.error}"
        return f"AI 分析失败: {result.error}"

    lines = ["**AI 分析**", ""]
    for label, content in _iter_sections(result):
        lines.extend([f"**{label}**", content, ""])
    return "\n".join(lines).strip()


def render_ai_analysis_feishu(result: AIAnalysisResult) -> str:
    return render_ai_analysis_markdown(result)


def render_ai_analysis_dingtalk(result: AIAnalysisResult) -> str:
    if not result.success:
        if result.skipped:
            return f"跳过: {result.error}"
        return f"AI 分析失败: {result.error}"

    lines = ["### AI 分析", ""]
    for label, content in _iter_sections(result):
        lines.extend([f"#### {label}", content, ""])
    return "\n".join(lines).strip()


def render_ai_analysis_html(result: AIAnalysisResult) -> str:
    if not result.success:
        css_class = "ai-info" if result.skipped else "ai-error"
        prefix = "跳过" if result.skipped else "错误"
        return f'<div class="{css_class}">{prefix} {_escape_html(result.error)}</div>'

    parts = ['<div class="ai-analysis">', '<h3>AI 分析</h3>']
    for label, content in _iter_sections(result):
        parts.extend(
            [
                '<div class="ai-section">',
                f"<h4>{_escape_html(label)}</h4>",
                f'<div class="ai-content">{_escape_html(content).replace(chr(10), "<br>")}</div>',
                '</div>',
            ]
        )
    parts.append('</div>')
    return "\n".join(parts)


def render_ai_analysis_plain(result: AIAnalysisResult) -> str:
    if not result.success:
        if result.skipped:
            return result.error
        return f"AI 分析失败: {result.error}"

    lines = ["AI 分析", ""]
    for label, content in _iter_sections(result):
        lines.extend([f"[{label}]", content, ""])
    return "\n".join(lines).strip()


def render_ai_analysis_telegram(result: AIAnalysisResult) -> str:
    if not result.success:
        if result.skipped:
            return f"跳过: {_escape_html(result.error)}"
        return f"AI 分析失败: {_escape_html(result.error)}"

    lines = ["<b>AI 分析</b>", ""]
    for label, content in _iter_sections(result):
        lines.extend([f"<b>{_escape_html(label)}</b>", _escape_html(content), ""])
    return "\n".join(lines).strip()


def render_ai_analysis_html_rich(result: AIAnalysisResult) -> str:
    if not result:
        return ""

    if not result.success:
        css_class = "ai-info" if result.skipped else "ai-error"
        prefix = "跳过" if result.skipped else "错误"
        return (
            '<div class="ai-section">'
            f'<div class="{css_class}">{prefix} {_escape_html(result.error)}</div>'
            '</div>'
        )

    parts = [
        '<div class="ai-section">',
        '  <div class="ai-section-header">',
        '    <div class="ai-section-title">AI 分析</div>',
        '    <span class="ai-section-badge">AI</span>',
        '  </div>',
        '  <div class="ai-blocks-grid">',
    ]

    for label, content in _iter_sections(result):
        content_html = _escape_html(content).replace("\n", "<br>")
        parts.extend(
            [
                '    <div class="ai-block">',
                f'      <div class="ai-block-title">{_escape_html(label)}</div>',
                f'      <div class="ai-block-content">{content_html}</div>',
                '    </div>',
            ]
        )

    parts.extend(['  </div>', '</div>'])
    return "\n".join(parts)


def get_ai_analysis_renderer(channel: str) -> Callable[[AIAnalysisResult], str]:
    renderers = {
        "feishu": render_ai_analysis_feishu,
        "dingtalk": render_ai_analysis_dingtalk,
        "wework": render_ai_analysis_markdown,
        "telegram": render_ai_analysis_telegram,
        "email": render_ai_analysis_html_rich,
        "ntfy": render_ai_analysis_markdown,
        "bark": render_ai_analysis_plain,
        "slack": render_ai_analysis_markdown,
    }
    return renderers.get(channel, render_ai_analysis_markdown)
