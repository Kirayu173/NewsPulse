# coding=utf-8
"""Render the simplified Chinese NewsPulse HTML report page."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Callable, Optional

from newspulse.workflow.render.helpers import html_escape
from newspulse.workflow.render.html_assets import _page_script, _page_styles
from newspulse.workflow.render.html_components import (
    _render_aggregate_insight,
    _render_overview_section,
    _render_story_feed,
    _render_summary_section,
    _rendered_summary_cards,
    _visible_cards,
)
from newspulse.workflow.render.html_formatters import _mode_label

if TYPE_CHECKING:
    from newspulse.workflow.render.models import RenderViewModel


def render_html_content(
    view_model: "RenderViewModel",
    update_info: Optional[dict] = None,
    *,
    region_order: Optional[list[str]] = None,
    get_time_func: Optional[Callable[[], datetime]] = None,
    show_new_section: bool = True,
) -> str:
    """Render the NewsPulse report as a simplified Chinese card-first HTML page."""

    if region_order is None:
        region_order = ["hotlist", "new_items", "standalone", "insight"]

    now = get_time_func() if get_time_func else datetime.now()
    cards = _visible_cards(view_model, region_order)

    sections: list[str] = []
    if cards:
        sections.append(
            _render_overview_section(
                view_model,
                cards,
                now=now,
                show_new_section=show_new_section,
            )
        )
        if "insight" in region_order:
            summary_html = _render_summary_section(view_model)
            if summary_html:
                sections.append(summary_html)
        sections.append(_render_story_feed(cards, show_new_section=show_new_section))

    if "insight" in region_order:
        aggregate_html = _render_aggregate_insight(view_model.insight)
        if aggregate_html:
            sections.append(aggregate_html)

    sections_html = (
        '<div class="empty-state">当前筛选下没有可展示的报告内容。</div>'
        if not sections
        else "".join(sections)
    )

    version_html = ""
    if update_info:
        version_html = (
            f'<div class="hero-banner">发现新版本 {html_escape(update_info["remote_version"])}，当前版本 {html_escape(update_info["current_version"])}</div>'
        )

    summary_card_count = len(_rendered_summary_cards(view_model))
    styles = _page_styles()
    script = _page_script()
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NewsPulse 新闻报告</title>
    <style>
{styles}
    </style>
</head>
<body>
    <div class="shell">
        <header class="hero">
            <h1>本批重点新闻分析</h1>
            <div class="hero-meta">
                <span class="hero-pill">{html_escape(view_model.report_type)}</span>
                <span class="hero-pill">模式：{html_escape(_mode_label(view_model.mode))}</span>
                <span class="hero-pill">新闻卡片：{len(cards)}</span>
                <span class="hero-pill">摘要卡片：{summary_card_count}</span>
            </div>
            {version_html}
        </header>
        <main class="content">
            {sections_html}
        </main>
        <footer class="footer">NewsPulse HTML 报告 · 由 Stage 6 ReportPackage 直接渲染</footer>
    </div>
    <script>
{script}
    </script>
</body>
</html>"""
