# coding=utf-8
"""Hotlist and new-item section renderers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from newspulse.report.helpers import html_escape

if TYPE_CHECKING:
    from newspulse.workflow.render.models import RenderGroupView


def render_hotlist_stats_html(groups: list["RenderGroupView"], display_mode: str = "keyword") -> str:
    """Render the hotlist statistics section."""
    if not groups:
        return ""

    total_count = len(groups)
    tab_bar_html = '<div class="tab-bar">'
    for tab_i, group in enumerate(groups):
        escaped_tab_word = html_escape(group.label)
        tab_count = group.count
        tab_bar_html += (
            f'<button class="tab-btn" data-tab-index="{tab_i}">'
            f'{escaped_tab_word}<span class="tab-count">{tab_count}</span></button>'
        )
    tab_bar_html += '<button class="tab-btn" data-tab-index="all">全部</button></div>'

    stats_html = ""
    for index, group in enumerate(groups, 1):
        count = group.count
        if count >= 10:
            count_class = "hot"
        elif count >= 5:
            count_class = "warm"
        else:
            count_class = ""

        escaped_word = html_escape(group.label)
        stats_html += f"""
                <div class="word-group" data-tab-index="{index - 1}">
                    <div class="word-header">
                        <div class="word-title">
                            <div class="word-name">{escaped_word}</div>
                            <div class="word-count {count_class}">{count} 条</div>
                        </div>
                        <div class="word-index"><span class="collapse-icon">▾</span>{index}/{total_count}</div>
                    </div>"""

        for title_index, item in enumerate(group.items, 1):
            new_class = "new" if item.is_new else ""
            stats_html += f"""
                    <div class="news-item {new_class}">
                        <div class="news-number">{title_index}</div>
                        <div class="news-content">
                            <div class="news-header">"""

            if display_mode == "keyword":
                stats_html += f'<span class="source-name">{html_escape(item.source_name)}</span>'
            elif item.matched_keyword:
                stats_html += f'<span class="keyword-tag">[{html_escape(item.matched_keyword)}]</span>'

            ranks = item.effective_ranks
            if ranks:
                min_rank = min(ranks)
                max_rank = max(ranks)
                if min_rank <= 3:
                    rank_class = "top"
                elif min_rank <= item.rank_threshold:
                    rank_class = "high"
                else:
                    rank_class = ""

                rank_text = str(min_rank) if min_rank == max_rank else f"{min_rank}-{max_rank}"
                stats_html += f'<span class="rank-num {rank_class}">{rank_text}</span>'

            if item.time_display:
                simplified_time = item.time_display.replace(" ~ ", "~").replace("[", "").replace("]", "")
                stats_html += f'<span class="time-info">{html_escape(simplified_time)}</span>'

            if item.count > 1:
                stats_html += f'<span class="count-info">{item.count}次</span>'

            stats_html += """
                            </div>
                            <div class="news-title">"""

            escaped_title = html_escape(item.title)
            if item.link_url:
                escaped_url = html_escape(item.link_url)
                stats_html += f'<a href="{escaped_url}" target="_blank" class="news-link">{escaped_title}</a>'
            else:
                stats_html += escaped_title

            stats_html += """
                            </div>
                        </div>
                    </div>"""

        stats_html += """
                </div>"""

    if not stats_html:
        return ""

    return f"""
                <div class="hotlist-section">{tab_bar_html}{stats_html}
                </div>"""


def render_new_titles_html(groups: list["RenderGroupView"], total_new_count: int) -> str:
    """Render the new-items section."""
    if not groups or total_new_count <= 0:
        return ""

    new_titles_html = f"""
                <div class="new-section">
                    <div class="new-section-title">本次新增热点 (共 {total_new_count} 条)</div>
                    <div class="new-sources-grid">"""

    for group in groups:
        escaped_source = html_escape(group.label)
        titles_count = len(group.items)
        new_titles_html += f"""
                    <div class="new-source-group">
                        <div class="new-source-title">{escaped_source} · {titles_count}条</div>"""

        for idx, item in enumerate(group.items, 1):
            ranks = item.effective_ranks
            rank_class = ""
            if ranks:
                min_rank = min(ranks)
                if min_rank <= 3:
                    rank_class = "top"
                elif min_rank <= item.rank_threshold:
                    rank_class = "high"
                rank_text = str(ranks[0]) if len(ranks) == 1 else f"{min(ranks)}-{max(ranks)}"
            else:
                rank_text = "?"

            new_titles_html += f"""
                        <div class="new-item">
                            <div class="new-item-number">{idx}</div>
                            <div class="new-item-rank {rank_class}">{rank_text}</div>
                            <div class="new-item-content">
                                <div class="new-item-title">"""

            escaped_title = html_escape(item.title)
            if item.link_url:
                escaped_url = html_escape(item.link_url)
                new_titles_html += f'<a href="{escaped_url}" target="_blank" class="news-link">{escaped_title}</a>'
            else:
                new_titles_html += escaped_title

            new_titles_html += """
                                </div>
                            </div>
                        </div>"""

        new_titles_html += """
                    </div>"""

    new_titles_html += """
                    </div>
                </div>"""
    return new_titles_html
