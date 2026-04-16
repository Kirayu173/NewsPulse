# coding=utf-8
"""Standalone hotlist section renderer."""

from typing import Dict, Optional

from newspulse.report.helpers import html_escape
from newspulse.utils.time import convert_time_for_display


def render_standalone_html(data: Optional[Dict]) -> str:
    """Render the standalone section for pinned hotlist platforms."""
    if not data:
        return ""

    platforms = data.get("platforms", [])
    if not platforms:
        return ""

    total_count = sum(len(platform.get("items", [])) for platform in platforms)
    if total_count == 0:
        return ""

    standalone_html = f'''
                <div class="standalone-section">
                    <div class="standalone-section-header">
                        <div class="standalone-section-title">独立展示区</div>
                        <div class="standalone-section-count">{total_count} 条</div>
                    </div>'''

    if len(platforms) >= 2:
        standalone_html += """
                    <div class="tab-bar standalone-tab-bar">"""
        for idx, platform in enumerate(platforms):
            items = platform.get("items", [])
            if not items:
                continue
            active = " active" if idx == 0 else ""
            name = html_escape(platform.get("name", platform.get("id", "")))
            standalone_html += (
                f'\n                        <button class="tab-btn{active}" data-standalone-tab="{idx}">'
                f'{name}<span class="tab-count">{len(items)}</span></button>'
            )
        standalone_html += f'''
                        <button class="tab-btn" data-standalone-tab="all">全部<span class="tab-count">{total_count}</span></button>
                    </div>'''

    standalone_html += """
                    <div class="standalone-groups-grid">"""

    for idx, platform in enumerate(platforms):
        platform_name = html_escape(platform.get("name", platform.get("id", "")))
        items = platform.get("items", [])
        if not items:
            continue

        standalone_html += f'''
                    <div class="standalone-group" data-standalone-tab="{idx}">
                        <div class="standalone-header">
                            <div class="standalone-name">{platform_name}</div>
                            <div class="standalone-count">{len(items)} 条</div>
                        </div>'''

        for item_index, item in enumerate(items, 1):
            title = html_escape(item.get("title", ""))
            url = html_escape(item.get("url", "") or item.get("mobileUrl", ""))
            ranks = item.get("ranks", [])
            first_time = item.get("first_time", "")
            last_time = item.get("last_time", "")
            count = item.get("count", 1)

            standalone_html += f'''
                        <div class="news-item">
                            <div class="news-number">{item_index}</div>
                            <div class="news-content">
                                <div class="news-header">'''

            if ranks:
                min_rank = min(ranks)
                max_rank = max(ranks)
                rank_class = "top" if min_rank <= 3 else "high" if min_rank <= 10 else ""
                rank_text = str(min_rank) if min_rank == max_rank else f"{min_rank}-{max_rank}"
                standalone_html += f'<span class="rank-num {rank_class}">{rank_text}</span>'

            if first_time and last_time and first_time != last_time:
                standalone_html += (
                    f'<span class="time-info">{html_escape(convert_time_for_display(first_time))}~{html_escape(convert_time_for_display(last_time))}</span>'
                )
            elif first_time:
                standalone_html += f'<span class="time-info">{html_escape(convert_time_for_display(first_time))}</span>'

            if count > 1:
                standalone_html += f'<span class="count-info">{count}次</span>'

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
