# coding=utf-8
"""Render the hotlist HTML report page."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Callable, List, Optional

from newspulse.report.helpers import html_escape
from newspulse.report.sections import (
    add_section_divider,
    render_hotlist_stats_html,
    render_new_titles_html,
    render_standalone_html,
)
from newspulse.workflow.render.insight import render_insight_html_rich

if TYPE_CHECKING:
    from newspulse.workflow.render.models import RenderViewModel


def _mode_label(mode: str) -> str:
    return {
        "daily": "日报",
        "current": "实时",
        "incremental": "增量",
    }.get(mode, mode)


def _render_failed_section(failed_ids: List[str]) -> str:
    if not failed_ids:
        return ""

    items = "".join(f"<li class=\"error-item\">{html_escape(item)}</li>" for item in failed_ids)
    return (
        "<div class=\"error-section\">"
        "<div class=\"error-title\">抓取失败来源</div>"
        f"<ul class=\"error-list\">{items}</ul>"
        "</div>"
    )


def render_html_content(
    view_model: "RenderViewModel",
    update_info: Optional[dict] = None,
    *,
    region_order: Optional[List[str]] = None,
    get_time_func: Optional[Callable[[], datetime]] = None,
    show_new_section: bool = True,
) -> str:
    """Render the hotlist report as a standalone HTML page."""

    if region_order is None:
        region_order = ["hotlist", "new_items", "standalone", "insight"]

    now = get_time_func() if get_time_func else datetime.now()
    failed_section = _render_failed_section(view_model.failed_source_names)
    hotlist_html = render_hotlist_stats_html(view_model.hotlist_groups, display_mode=view_model.display_mode)
    new_items_html = ""
    if show_new_section:
        new_items_html = render_new_titles_html(view_model.new_item_groups, view_model.total_new_items)
    standalone_html = render_standalone_html(view_model.standalone_groups)
    ai_html = render_insight_html_rich(view_model.insight)

    region_contents = {
        "hotlist": hotlist_html,
        "new_items": new_items_html,
        "standalone": standalone_html,
        "insight": ai_html,
    }

    sections: List[str] = []
    if failed_section:
        sections.append(failed_section)

    has_previous_content = bool(failed_section)
    for region in region_order:
        content = region_contents.get(region, "")
        if not content:
            continue
        if has_previous_content:
            content = add_section_divider(content)
        sections.append(content)
        has_previous_content = True

    sections_html = "<div class=\"empty-state\">当前没有可展示的内容</div>" if not sections else "\n".join(sections)

    version_html = ""
    if update_info:
        version_html = (
            f"<div class=\"update-banner\">发现新版本 {html_escape(update_info['remote_version'])}，"
            f"当前版本 {html_escape(update_info['current_version'])}</div>"
        )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NewsPulse 热榜报告</title>
    <style>
        :root {{
            --bg: #f4efe7;
            --paper: #fffdf8;
            --ink: #1f2937;
            --muted: #6b7280;
            --line: #e5ded1;
            --accent: #bf5b04;
            --accent-soft: #f7e1c8;
            --accent-strong: #8f3b00;
            --danger: #b91c1c;
            --shadow: 0 18px 45px rgba(86, 53, 24, 0.12);
        }}

        * {{ box-sizing: border-box; }}

        body {{
            margin: 0;
            padding: 20px;
            background:
                radial-gradient(circle at top left, rgba(191, 91, 4, 0.08), transparent 35%),
                linear-gradient(180deg, #f8f3eb 0%, var(--bg) 100%);
            color: var(--ink);
            font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
            line-height: 1.6;
        }}

        .container {{
            max-width: 920px;
            margin: 0 auto;
            background: var(--paper);
            border: 1px solid rgba(143, 59, 0, 0.08);
            border-radius: 28px;
            overflow: hidden;
            box-shadow: var(--shadow);
        }}

        .header {{
            padding: 36px 32px 28px;
            background: linear-gradient(135deg, rgba(191, 91, 4, 0.96), rgba(137, 56, 0, 0.92));
            color: #fff;
        }}

        .header-title {{
            margin: 0;
            font-size: clamp(28px, 4vw, 40px);
            font-weight: 800;
            letter-spacing: 0.02em;
        }}

        .header-subtitle {{
            margin-top: 10px;
            font-size: 15px;
            opacity: 0.88;
        }}

        .header-grid {{
            margin-top: 24px;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 12px;
        }}

        .header-card {{
            padding: 14px 16px;
            border-radius: 18px;
            background: rgba(255, 255, 255, 0.12);
            border: 1px solid rgba(255, 255, 255, 0.18);
            backdrop-filter: blur(8px);
        }}

        .header-card-label {{
            font-size: 12px;
            opacity: 0.78;
            margin-bottom: 6px;
        }}

        .header-card-value {{
            font-size: 18px;
            font-weight: 700;
        }}

        .update-banner {{
            margin-top: 16px;
            padding: 10px 14px;
            border-radius: 14px;
            background: rgba(255, 255, 255, 0.16);
            border: 1px solid rgba(255, 255, 255, 0.2);
            font-size: 14px;
        }}

        .content {{
            padding: 28px 28px 36px;
        }}

        .empty-state {{
            padding: 40px 24px;
            text-align: center;
            color: var(--muted);
            font-size: 16px;
        }}

        .section-divider {{
            margin-top: 28px;
            padding-top: 24px;
            border-top: 1px dashed var(--line);
        }}

        .error-section {{
            padding: 18px 20px;
            border-radius: 20px;
            border: 1px solid rgba(185, 28, 28, 0.16);
            background: rgba(185, 28, 28, 0.06);
        }}

        .error-title {{
            font-size: 15px;
            font-weight: 700;
            color: var(--danger);
            margin-bottom: 10px;
        }}

        .error-list {{
            margin: 0;
            padding-left: 20px;
        }}

        .error-item {{
            color: #7f1d1d;
            margin: 4px 0;
        }}

        .tab-bar {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-bottom: 18px;
        }}

        .tab-btn {{
            border: 0;
            border-radius: 999px;
            padding: 9px 14px;
            background: #f2eadf;
            color: #6b4f32;
            cursor: pointer;
            font-size: 13px;
            font-weight: 600;
            transition: all 0.18s ease;
        }}

        .tab-btn:hover {{
            background: #ead8c3;
        }}

        .tab-btn.active {{
            background: var(--accent);
            color: #fff;
            box-shadow: 0 8px 20px rgba(191, 91, 4, 0.22);
        }}

        .tab-count {{
            margin-left: 6px;
            font-size: 12px;
            opacity: 0.8;
        }}

        .hotlist-section,
        .new-section,
        .standalone-section,
        .ai-section {{
            padding: 22px 22px 8px;
            border-radius: 24px;
            background: linear-gradient(180deg, rgba(255,255,255,0.95), rgba(249,243,233,0.92));
            border: 1px solid rgba(191, 91, 4, 0.08);
        }}

        .word-group,
        .standalone-group {{
            margin-bottom: 20px;
        }}

        .word-header,
        .standalone-header,
        .standalone-section-header,
        .ai-section-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            margin-bottom: 14px;
        }}

        .word-title {{
            display: flex;
            align-items: center;
            gap: 10px;
            flex-wrap: wrap;
        }}

        .word-name,
        .standalone-name,
        .standalone-section-title,
        .ai-section-title {{
            font-size: 18px;
            font-weight: 800;
            color: #2a2116;
        }}

        .word-count,
        .standalone-count,
        .standalone-section-count {{
            color: var(--accent-strong);
            font-size: 13px;
            font-weight: 700;
            background: var(--accent-soft);
            padding: 4px 10px;
            border-radius: 999px;
        }}

        .word-index {{
            color: var(--muted);
            font-size: 12px;
        }}

        .news-item,
        .new-item {{
            display: flex;
            gap: 12px;
            padding: 12px 0;
            border-bottom: 1px solid rgba(229, 222, 209, 0.7);
            align-items: flex-start;
        }}

        .news-item:last-child,
        .new-item:last-child {{
            border-bottom: 0;
        }}

        .news-item.new {{
            position: relative;
        }}

        .news-item.new::after {{
            content: "NEW";
            position: absolute;
            top: 10px;
            right: 0;
            font-size: 10px;
            font-weight: 800;
            color: var(--accent-strong);
            background: #fde68a;
            padding: 3px 7px;
            border-radius: 999px;
        }}

        .news-number,
        .new-item-number {{
            width: 28px;
            min-width: 28px;
            height: 28px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 999px;
            background: #f3ede4;
            color: #7a5b3f;
            font-size: 13px;
            font-weight: 700;
            margin-top: 2px;
        }}

        .news-content,
        .new-item-content {{
            flex: 1;
            min-width: 0;
        }}

        .news-header {{
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            margin-bottom: 6px;
        }}

        .source-name,
        .time-info,
        .count-info {{
            font-size: 12px;
            color: var(--muted);
        }}

        .keyword-tag {{
            font-size: 12px;
            color: var(--accent-strong);
            background: var(--accent-soft);
            padding: 2px 8px;
            border-radius: 999px;
        }}

        .rank-num,
        .new-item-rank {{
            font-size: 11px;
            font-weight: 700;
            border-radius: 999px;
            padding: 4px 8px;
            background: #e5e7eb;
            color: #374151;
        }}

        .rank-num.top,
        .new-item-rank.top {{
            background: #fee2e2;
            color: #b91c1c;
        }}

        .rank-num.high,
        .new-item-rank.high {{
            background: #ffedd5;
            color: #c2410c;
        }}

        .news-title,
        .new-item-title {{
            font-size: 15px;
            font-weight: 600;
            color: #221a11;
        }}

        .news-link {{
            color: #93440c;
            text-decoration: none;
        }}

        .news-link:hover {{
            text-decoration: underline;
        }}

        .new-section-title {{
            font-size: 18px;
            font-weight: 800;
            margin-bottom: 14px;
        }}

        .new-sources-grid,
        .standalone-groups-grid,
        .ai-blocks-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 16px;
        }}

        .new-source-group {{
            padding: 16px;
            border-radius: 18px;
            background: #fffaf2;
            border: 1px solid rgba(191, 91, 4, 0.08);
        }}

        .new-source-title {{
            font-size: 14px;
            font-weight: 700;
            margin-bottom: 10px;
            color: #5c452d;
        }}

        .ai-section-badge {{
            padding: 4px 10px;
            border-radius: 999px;
            background: #fde68a;
            color: #854d0e;
            font-size: 12px;
            font-weight: 700;
        }}

        .ai-block {{
            padding: 16px;
            border-radius: 18px;
            background: #fffaf2;
            border: 1px solid rgba(191, 91, 4, 0.08);
        }}

        .ai-block-title {{
            font-size: 14px;
            font-weight: 800;
            margin-bottom: 10px;
            color: #51331b;
        }}

        .ai-block-content {{
            font-size: 14px;
            color: #3b2b1b;
            line-height: 1.7;
        }}

        .ai-info,
        .ai-error {{
            padding: 14px 16px;
            border-radius: 16px;
            font-size: 14px;
        }}

        .ai-info {{
            background: #eff6ff;
            color: #1d4ed8;
        }}

        .ai-error {{
            background: #fef2f2;
            color: #b91c1c;
        }}

        .footer {{
            padding: 20px 28px 28px;
            color: var(--muted);
            font-size: 13px;
            text-align: center;
        }}

        @media (max-width: 720px) {{
            body {{ padding: 14px; }}
            .header {{ padding: 28px 22px 22px; }}
            .content {{ padding: 20px; }}
            .hotlist-section,
            .new-section,
            .standalone-section,
            .ai-section {{ padding: 18px 16px 6px; }}
            .new-sources-grid,
            .standalone-groups-grid,
            .ai-blocks-grid {{ grid-template-columns: 1fr; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header class="header">
            <h1 class="header-title">NewsPulse 热榜报告</h1>
            <div class="header-subtitle">热榜追踪 + 聚合分析 + AI 洞察</div>
            <div class="header-grid">
                <div class="header-card">
                    <div class="header-card-label">模式</div>
                    <div class="header-card-value">{html_escape(_mode_label(view_model.mode))}</div>
                </div>
                <div class="header-card">
                    <div class="header-card-label">标题数</div>
                    <div class="header-card-value">{view_model.total_titles}</div>
                </div>
                <div class="header-card">
                    <div class="header-card-label">生成时间</div>
                    <div class="header-card-value">{html_escape(now.strftime('%Y-%m-%d %H:%M:%S'))}</div>
                </div>
            </div>
            {version_html}
        </header>

        <main class="content">
            {sections_html}
        </main>

        <footer class="footer">© NewsPulse · 当前版本仅保留热榜数据源</footer>
    </div>

    <script>
        function initTabGroup(barSelector, itemSelector, dataKey) {{
            document.querySelectorAll(barSelector).forEach(function(bar) {{
                var buttons = Array.from(bar.querySelectorAll('.tab-btn'));
                var container = bar.parentElement;
                var items = Array.from(container.querySelectorAll(itemSelector));
                if (!buttons.length || !items.length) return;

                function activate(button) {{
                    var value = button.dataset[dataKey];
                    buttons.forEach(function(item) {{
                        item.classList.toggle('active', item === button);
                    }});
                    items.forEach(function(item) {{
                        if (value === 'all') {{
                            item.style.display = '';
                        }} else {{
                            item.style.display = item.dataset[dataKey] === value ? '' : 'none';
                        }}
                    }});
                }}

                buttons.forEach(function(button) {{
                    button.addEventListener('click', function() {{
                        activate(button);
                    }});
                }});

                activate(buttons[0]);
            }});
        }}

        document.addEventListener('DOMContentLoaded', function() {{
            initTabGroup('.hotlist-section > .tab-bar', '.word-group', 'tabIndex');
            initTabGroup('.standalone-tab-bar', '.standalone-group', 'standaloneTab');
        }});
    </script>
</body>
</html>"""
