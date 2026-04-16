# coding=utf-8
"""Hotlist and new-item section renderers."""

from typing import Dict, List

from newspulse.report.helpers import html_escape


def render_hotlist_stats_html(stats: List[Dict], display_mode: str = "keyword") -> str:
    """Render the hotlist statistics section."""
    if not stats:
        return ""

    total_count = len(stats)
    tab_bar_html = '<div class="tab-bar">'
    for tab_i, tab_stat in enumerate(stats):
        escaped_tab_word = html_escape(tab_stat["word"])
        tab_count = tab_stat["count"]
        tab_bar_html += (
            f'<button class="tab-btn" data-tab-index="{tab_i}">'
            f"{escaped_tab_word}<span class=\"tab-count\">{tab_count}</span></button>"
        )
    tab_bar_html += '<button class="tab-btn" data-tab-index="all">\u5168\u90e8</button></div>'

    stats_html = ""
    for i, stat in enumerate(stats, 1):
        count = stat["count"]
        if count >= 10:
            count_class = "hot"
        elif count >= 5:
            count_class = "warm"
        else:
            count_class = ""

        escaped_word = html_escape(stat["word"])
        stats_html += f"""
                <div class="word-group" data-tab-index="{i - 1}">
                    <div class="word-header">
                        <div class="word-title">
                            <div class="word-name">{escaped_word}</div>
                            <div class="word-count {count_class}">{count} \u6761</div>
                        </div>
                        <div class="word-index"><span class="collapse-icon">\u25be</span>{i}/{total_count}</div>
                    </div>"""

        for j, title_data in enumerate(stat["titles"], 1):
            is_new = title_data.get("is_new", False)
            new_class = "new" if is_new else ""

            stats_html += f"""
                    <div class="news-item {new_class}">
                        <div class="news-number">{j}</div>
                        <div class="news-content">
                            <div class="news-header">"""

            if display_mode == "keyword":
                stats_html += (
                    f'<span class="source-name">{html_escape(title_data["source_name"])}</span>'
                )
            else:
                matched_keyword = title_data.get("matched_keyword", "")
                if matched_keyword:
                    stats_html += (
                        f'<span class="keyword-tag">[{html_escape(matched_keyword)}]</span>'
                    )

            ranks = title_data.get("ranks", [])
            if ranks:
                min_rank = min(ranks)
                max_rank = max(ranks)
                rank_threshold = title_data.get("rank_threshold", 10)
                if min_rank <= 3:
                    rank_class = "top"
                elif min_rank <= rank_threshold:
                    rank_class = "high"
                else:
                    rank_class = ""

                rank_text = str(min_rank) if min_rank == max_rank else f"{min_rank}-{max_rank}"
                stats_html += f'<span class="rank-num {rank_class}">{rank_text}</span>'

            time_display = title_data.get("time_display", "")
            if time_display:
                simplified_time = (
                    time_display.replace(" ~ ", "~")
                    .replace("[", "")
                    .replace("]", "")
                )
                stats_html += (
                    f'<span class="time-info">{html_escape(simplified_time)}</span>'
                )

            count_info = title_data.get("count", 1)
            if count_info > 1:
                stats_html += f'<span class="count-info">{count_info}\u6b21</span>'

            stats_html += """
                            </div>
                            <div class="news-title">"""

            escaped_title = html_escape(title_data["title"])
            link_url = title_data.get("mobile_url") or title_data.get("url", "")
            if link_url:
                escaped_url = html_escape(link_url)
                stats_html += (
                    f'<a href="{escaped_url}" target="_blank" class="news-link">{escaped_title}</a>'
                )
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


def render_new_titles_html(new_titles: List[Dict], total_new_count: int) -> str:
    """Render the new-items section."""
    if not new_titles:
        return ""

    new_titles_html = f"""
                <div class="new-section">
                    <div class="new-section-title">\u672c\u6b21\u65b0\u589e\u70ed\u70b9 (\u5171 {total_new_count} \u6761)</div>
                    <div class="new-sources-grid">"""

    for source_data in new_titles:
        escaped_source = html_escape(source_data["source_name"])
        titles_count = len(source_data["titles"])

        new_titles_html += f"""
                    <div class="new-source-group">
                        <div class="new-source-title">{escaped_source} \u00b7 {titles_count}\u6761</div>"""

        for idx, title_data in enumerate(source_data["titles"], 1):
            ranks = title_data.get("ranks", [])
            rank_class = ""
            if ranks:
                min_rank = min(ranks)
                if min_rank <= 3:
                    rank_class = "top"
                elif min_rank <= title_data.get("rank_threshold", 10):
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

            escaped_title = html_escape(title_data["title"])
            link_url = title_data.get("mobile_url") or title_data.get("url", "")
            if link_url:
                escaped_url = html_escape(link_url)
                new_titles_html += (
                    f'<a href="{escaped_url}" target="_blank" class="news-link">{escaped_title}</a>'
                )
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
