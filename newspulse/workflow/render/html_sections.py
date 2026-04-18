# coding=utf-8
"""HTML section renderers shared by the workflow render stage."""

from __future__ import annotations

from typing import TYPE_CHECKING

from newspulse.workflow.render.helpers import html_escape

if TYPE_CHECKING:
    from newspulse.workflow.render.models import RenderGroupView


def add_section_divider(content: str) -> str:
    """Inject the shared divider class into a section wrapper."""
    if not content or 'class="' not in content:
        return content

    first_class_pos = content.find('class="')
    if first_class_pos == -1:
        return content

    insert_pos = first_class_pos + len('class="')
    return content[:insert_pos] + "section-divider " + content[insert_pos:]


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
    tab_bar_html += '<button class="tab-btn" data-tab-index="all">鍏ㄩ儴</button></div>'

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
                            <div class="word-count {count_class}">{count} 鏉?/div>
                        </div>
                        <div class="word-index"><span class="collapse-icon">鈻?/span>{index}/{total_count}</div>
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
                stats_html += f'<span class="count-info">{item.count}娆?/span>'

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
                    <div class="new-section-title">鏈鏂板鐑偣 (鍏?{total_new_count} 鏉?</div>
                    <div class="new-sources-grid">"""

    for group in groups:
        if not group.items:
            continue

        new_titles_html += f"""
                        <div class="new-source-group">
                            <div class="new-source-title">{html_escape(group.label)} ({len(group.items)} 鏉?/div>"""

        for index, item in enumerate(group.items, 1):
            title = html_escape(item.title)
            url = html_escape(item.link_url)
            ranks = item.effective_ranks
            rank_badge = ""
            if ranks:
                min_rank = min(ranks)
                max_rank = max(ranks)
                rank_class = "top" if min_rank <= 3 else "high" if min_rank <= item.rank_threshold else ""
                rank_text = str(min_rank) if min_rank == max_rank else f"{min_rank}-{max_rank}"
                rank_badge = f'<span class="new-item-rank {rank_class}">{rank_text}</span>'

            new_titles_html += f"""
                            <div class="new-item">
                                <div class="new-item-number">{index}</div>
                                <div class="new-item-content">
                                    <div class="news-header">{rank_badge}</div>
                                    <div class="new-item-title">"""

            if url:
                new_titles_html += f'<a href="{url}" target="_blank" class="news-link">{title}</a>'
            else:
                new_titles_html += title

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
                        <div class="standalone-section-title">鐙珛灞曠ず鍖?/div>
                        <div class="standalone-section-count">{total_count} 鏉?/div>
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
                        <button class="tab-btn" data-standalone-tab="all">鍏ㄩ儴<span class="tab-count">{total_count}</span></button>
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
                            <div class="standalone-count">{len(group.items)} 鏉?/div>
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
                standalone_html += f'<span class="count-info">{item.count}娆?/span>'

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


__all__ = [
    "add_section_divider",
    "render_hotlist_stats_html",
    "render_new_titles_html",
    "render_standalone_html",
]
