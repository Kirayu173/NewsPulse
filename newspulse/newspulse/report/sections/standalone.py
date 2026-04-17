# coding=utf-8
"""Standalone hotlist section renderer."""

from __future__ import annotations

from typing import TYPE_CHECKING

from newspulse.report.helpers import html_escape

if TYPE_CHECKING:
    from newspulse.workflow.render.models import RenderGroupView


def render_standalone_html(groups: list["RenderGroupView"]) -> str:
    """Render the standalone section for pinned hotlist platforms."""
    if not groups:
        return ""

    total_count = sum(len(group.items) for group in groups)
    if total_count == 0:
        return ""

    standalone_html = f"""
                <div class="standalone-section">
                    <div class="standalone-section-header">
                        <div class="standalone-section-title">独立展示区</div>
                        <div class="standalone-section-count">{total_count} 条</div>
                    </div>"""

    if len(groups) >= 2:
        standalone_html += """
                    <div class="tab-bar standalone-tab-bar">"""
        for idx, group in enumerate(groups):
            if not group.items:
                continue
            active = " active" if idx == 0 else ""
            name = html_escape(group.label)
            standalone_html += (
                f'\n                        <button class="tab-btn{active}" data-standalone-tab="{idx}">'
                f'{name}<span class="tab-count">{len(group.items)}</span></button>'
            )
        standalone_html += f"""
                        <button class="tab-btn" data-standalone-tab="all">全部<span class="tab-count">{total_count}</span></button>
                    </div>"""

    standalone_html += """
                    <div class="standalone-groups-grid">"""

    for idx, group in enumerate(groups):
        if not group.items:
            continue

        standalone_html += f"""
                    <div class="standalone-group" data-standalone-tab="{idx}">
                        <div class="standalone-header">
                            <div class="standalone-name">{html_escape(group.label)}</div>
                            <div class="standalone-count">{len(group.items)} 条</div>
                        </div>"""

        for item_index, item in enumerate(group.items, 1):
            title = html_escape(item.title)
            url = html_escape(item.link_url)
            ranks = item.effective_ranks

            standalone_html += f"""
                        <div class="news-item">
                            <div class="news-number">{item_index}</div>
                            <div class="news-content">
                                <div class="news-header">"""

            if ranks:
                min_rank = min(ranks)
                max_rank = max(ranks)
                rank_class = "top" if min_rank <= 3 else "high" if min_rank <= item.rank_threshold else ""
                rank_text = str(min_rank) if min_rank == max_rank else f"{min_rank}-{max_rank}"
                standalone_html += f'<span class="rank-num {rank_class}">{rank_text}</span>'

            if item.time_display:
                simplified_time = item.time_display.replace(" ~ ", "~").replace("[", "").replace("]", "")
                standalone_html += f'<span class="time-info">{html_escape(simplified_time)}</span>'

            if item.count > 1:
                standalone_html += f'<span class="count-info">{item.count}次</span>'

            standalone_html += """
                                </div>
                                <div class="news-title">"""

            if url:
                standalone_html += f'<a href="{url}" target="_blank" class="news-link">{title}</a>'
            else:
                standalone_html += title

            standalone_html += """
                                </div>
                            </div>
                        </div>"""

        standalone_html += """
                    </div>"""

    standalone_html += """
                    </div>
                </div>"""
    return standalone_html
