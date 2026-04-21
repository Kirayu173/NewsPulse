# coding=utf-8
"""Render the simplified Chinese NewsPulse HTML report page."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Callable, Iterable, Optional

from newspulse.workflow.render.helpers import html_escape

if TYPE_CHECKING:
    from newspulse.workflow.render.models import (
        RenderInsightSectionView,
        RenderInsightView,
        RenderNewsCardView,
        RenderViewModel,
    )


def _mode_label(mode: str) -> str:
    return {
        "daily": "日报",
        "current": "实时",
        "incremental": "增量",
    }.get(mode, mode)


def _rank_text(card: "RenderNewsCardView") -> str:
    ranks = card.item.effective_ranks
    if not ranks:
        return "排名未知"
    best = min(ranks)
    worst = max(ranks)
    if best == worst:
        return f"第 {best} 名"
    return f"第 {best}-{worst} 名"


def _rank_timeline_text(card: "RenderNewsCardView") -> str:
    timeline = card.item.rank_timeline
    if not timeline:
        return ""

    pieces: list[str] = []
    for entry in timeline[:4]:
        time_text = str(entry.get("time", "") or "").strip()
        rank_text = str(entry.get("rank", "") or "").strip()
        if time_text and rank_text:
            pieces.append(f"{time_text} #{rank_text}")
    return " · ".join(pieces)


def _confidence_text(confidence: float) -> str:
    if confidence <= 0:
        return ""
    return f"{round(confidence * 100)}%"


def _render_badges(card: "RenderNewsCardView", *, show_new_section: bool) -> str:
    badges: list[str] = [
        f'<span class="story-badge source">{html_escape(card.item.source_name or card.item.source_id or "未知来源")}</span>'
    ]
    if show_new_section and card.is_new:
        badges.append('<span class="story-badge accent">新增</span>')
    if card.is_standalone:
        badges.append('<span class="story-badge muted">独立保留</span>')
    return "".join(badges)


def _render_meta_row(card: "RenderNewsCardView") -> str:
    parts: list[str] = [f"排名 {_rank_text(card)}"]
    if card.item.time_display:
        cleaned_time = card.item.time_display.replace("[", "").replace("]", "")
        parts.append(f"时间 {cleaned_time}")
    if card.item.count > 1:
        parts.append(f"出现 {card.item.count} 次")
    timeline_text = _rank_timeline_text(card)
    if timeline_text:
        parts.append(f"轨迹 {timeline_text}")
    return "".join(
        f'<span class="story-meta-pill">{html_escape(part)}</span>' for part in parts
    )


def _render_action_links(card: "RenderNewsCardView") -> str:
    links: list[str] = []
    if card.item.url:
        links.append(
            f'<a class="story-action" href="{html_escape(card.item.url)}" target="_blank" rel="noreferrer">查看原文</a>'
        )
    if card.item.mobile_url and card.item.mobile_url != card.item.url:
        links.append(
            f'<a class="story-action secondary" href="{html_escape(card.item.mobile_url)}" target="_blank" rel="noreferrer">移动端</a>'
        )
    return "".join(links)


def _render_bullet_list(items: Iterable[str], css_class: str) -> str:
    normalized = [html_escape(str(item)) for item in items if str(item or "").strip()]
    if not normalized:
        return ""
    rows = "".join(f"<li>{item}</li>" for item in normalized)
    return f'<ul class="{css_class}">{rows}</ul>'


def _render_analysis_panel(card: "RenderNewsCardView") -> str:
    analysis = card.analysis
    rows: list[str] = [
        '<section class="analysis-panel">',
        '<h3>LLM Analysis</h3>',
    ]

    if analysis.visible:
        if analysis.what_happened:
            rows.append('<div class="panel-subtitle">发生了什么</div>')
            rows.append(
                f'<p class="panel-body lead">{html_escape(analysis.what_happened)}</p>'
            )
        if analysis.why_it_matters:
            rows.append('<div class="panel-subtitle">为什么重要</div>')
            rows.append(f'<p class="panel-body">{html_escape(analysis.why_it_matters)}</p>')
        if analysis.key_facts:
            rows.append('<div class="panel-subtitle">关键信息</div>')
            rows.append(_render_bullet_list(analysis.key_facts, "bullet-list"))
        if analysis.watchpoints:
            rows.append('<div class="panel-subtitle">后续观察</div>')
            rows.append(_render_bullet_list(analysis.watchpoints, "bullet-list compact"))
        if analysis.uncertainties:
            rows.append('<div class="panel-subtitle">不确定点</div>')
            rows.append(_render_bullet_list(analysis.uncertainties, "bullet-list compact"))
        if analysis.evidence:
            rows.append('<div class="panel-subtitle">支撑依据</div>')
            rows.append(_render_bullet_list(analysis.evidence, "bullet-list compact"))
        confidence_text = _confidence_text(analysis.confidence)
        if confidence_text:
            rows.append(
                f'<div class="confidence-pill">分析置信度 {html_escape(confidence_text)}</div>'
            )
    else:
        rows.append('<p class="panel-placeholder">这条新闻暂未生成 LLM Analysis。</p>')

    rows.append("</section>")
    return "".join(rows)


def _render_story_card(card: "RenderNewsCardView", index: int, *, show_new_section: bool) -> str:
    source_summary = card.source_summary or card.item.summary
    summary_html = (
        f'<p class="story-summary">{html_escape(source_summary)}</p>'
        if source_summary
        else ""
    )

    return f"""
    <article class="story-card" id="story-{html_escape(card.item.news_item_id)}">
        <div class="story-head">
            <div class="story-index">{index:02d}</div>
            <div class="story-main">
                <div class="story-badges">{_render_badges(card, show_new_section=show_new_section)}</div>
                <h2 class="story-title">{html_escape(card.item.title)}</h2>
                {summary_html}
                <div class="story-meta-row">{_render_meta_row(card)}</div>
                <div class="story-actions">{_render_action_links(card)}</div>
            </div>
        </div>
        {_render_analysis_panel(card)}
    </article>
    """


def _visible_cards(view_model: "RenderViewModel", region_order: list[str]) -> list["RenderNewsCardView"]:
    include_hotlist = "hotlist" in region_order
    include_standalone = "standalone" in region_order
    rows: list[RenderNewsCardView] = []
    seen_ids: set[str] = set()
    for card in view_model.news_cards:
        visible = (include_hotlist and card.is_selected) or (
            include_standalone and card.is_standalone
        )
        if not visible:
            continue
        item_id = str(card.item.news_item_id or "").strip()
        if item_id in seen_ids:
            continue
        seen_ids.add(item_id)
        rows.append(card)
    return rows


def _render_overview_section(
    view_model: "RenderViewModel",
    cards: list["RenderNewsCardView"],
    *,
    now: datetime,
    show_new_section: bool,
) -> str:
    new_count = sum(1 for card in cards if card.is_new)
    analyzed_count = sum(1 for card in cards if card.analysis.visible)
    return f"""
    <section class="overview-strip">
        <div class="overview-card">
            <div class="overview-label">模式</div>
            <div class="overview-value">{html_escape(_mode_label(view_model.mode))}</div>
        </div>
        <div class="overview-card">
            <div class="overview-label">当前新闻数</div>
            <div class="overview-value">{len(cards)}</div>
        </div>
        <div class="overview-card">
            <div class="overview-label">已分析条数</div>
            <div class="overview-value">{analyzed_count}</div>
        </div>
        <div class="overview-card">
            <div class="overview-label">新增新闻</div>
            <div class="overview-value">{new_count if show_new_section else "-"}</div>
        </div>
        <div class="overview-card">
            <div class="overview-label">生成时间</div>
            <div class="overview-value small">{html_escape(now.strftime("%Y-%m-%d %H:%M:%S"))}</div>
        </div>
    </section>
    """


def _render_story_feed(cards: list["RenderNewsCardView"], *, show_new_section: bool) -> str:
    if not cards:
        return ""
    stories = "".join(
        _render_story_card(card, index, show_new_section=show_new_section)
        for index, card in enumerate(cards, start=1)
    )
    return f"""
    <section class="story-feed">
        <h2>新闻卡片</h2>
        <div class="story-list">{stories}</div>
    </section>
    """


def _render_insight_sections(sections: Iterable["RenderInsightSectionView"]) -> str:
    blocks: list[str] = []
    for section in sections:
        blocks.append(
            f"""
            <article class="aggregate-card">
                <h3>{html_escape(section.title or section.key)}</h3>
                <p>{html_escape(section.content)}</p>
            </article>
            """
        )
    return "".join(blocks)


def _render_aggregate_insight(insight: "RenderInsightView") -> str:
    if insight.status in {"skipped", "error"} and not insight.sections:
        status_title = "聚合分析已跳过" if insight.status == "skipped" else "聚合分析生成失败"
        return f"""
        <section class="aggregate-section">
            <h2>{status_title}</h2>
            <p class="aggregate-note">{html_escape(insight.message or "暂无可展示内容。")}</p>
        </section>
        """
    if not insight.sections:
        return ""

    stats_bits: list[str] = []
    analyzed_news = int(insight.stats.get("analyzed_news", 0) or 0)
    total_news = int(insight.stats.get("total_news", 0) or 0)
    if analyzed_news > 0:
        if total_news and total_news >= analyzed_news:
            stats_bits.append(f"已分析 {analyzed_news}/{total_news}")
        else:
            stats_bits.append(f"已分析 {analyzed_news}")
    max_news_limit = int(insight.stats.get("max_news_limit", 0) or 0)
    if max_news_limit > 0:
        stats_bits.append(f"上限 {max_news_limit}")
    stats_html = "".join(
        f'<span class="mini-chip">{html_escape(bit)}</span>' for bit in stats_bits
    )

    return f"""
    <section class="aggregate-section">
        <div class="aggregate-head">
            <h2>综合判断</h2>
            <div class="chip-row">{stats_html}</div>
        </div>
        <div class="aggregate-grid">{_render_insight_sections(insight.sections)}</div>
    </section>
    """


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
        sections.append(_render_story_feed(cards, show_new_section=show_new_section))

    if "insight" in region_order:
        aggregate_html = _render_aggregate_insight(view_model.insight)
        if aggregate_html:
            sections.append(aggregate_html)

    if not sections:
        sections_html = '<div class="empty-state">当前筛选下没有可展示的报告内容。</div>'
    else:
        sections_html = "".join(sections)

    version_html = ""
    if update_info:
        version_html = (
            f'<div class="hero-banner">发现新版本 {html_escape(update_info["remote_version"])}，当前版本 {html_escape(update_info["current_version"])}</div>'
        )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NewsPulse 新闻报告</title>
    <style>
        :root {{
            --bg: #f4efe8;
            --paper: #fffdf9;
            --panel: #fff8f0;
            --panel-strong: #fff5e7;
            --ink: #17202d;
            --muted: #697383;
            --accent: #c35b17;
            --accent-deep: #8d3600;
            --accent-soft: #f6dcc4;
            --border: rgba(195, 91, 23, 0.12);
            --shadow: 0 24px 70px rgba(59, 31, 8, 0.10);
        }}

        * {{ box-sizing: border-box; }}

        body {{
            margin: 0;
            padding: 22px;
            color: var(--ink);
            background:
                radial-gradient(circle at 10% 10%, rgba(195, 91, 23, 0.12), transparent 30%),
                radial-gradient(circle at 90% 18%, rgba(38, 91, 122, 0.08), transparent 26%),
                linear-gradient(180deg, #f8f3ec 0%, var(--bg) 100%);
            font-family: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
            line-height: 1.7;
        }}

        h1, h2, h3 {{
            font-family: "Source Han Serif SC", "Songti SC", "Noto Serif CJK SC", serif;
        }}

        .shell {{
            max-width: 1120px;
            margin: 0 auto;
            background: var(--paper);
            border: 1px solid var(--border);
            border-radius: 32px;
            overflow: hidden;
            box-shadow: var(--shadow);
        }}

        .hero {{
            position: relative;
            overflow: hidden;
            padding: 44px 38px 34px;
            background:
                radial-gradient(circle at top right, rgba(255, 255, 255, 0.18), transparent 30%),
                linear-gradient(135deg, rgba(195, 91, 23, 0.98), rgba(118, 52, 15, 0.94));
            color: #fff;
        }}

        .hero::after {{
            content: "";
            position: absolute;
            inset: auto -90px -110px auto;
            width: 260px;
            height: 260px;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.10);
            filter: blur(8px);
        }}

        .hero h1 {{
            position: relative;
            z-index: 1;
            margin: 0;
            font-size: clamp(30px, 5vw, 48px);
            line-height: 1.08;
            letter-spacing: -0.03em;
        }}

        .hero-meta {{
            position: relative;
            z-index: 1;
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 20px;
        }}

        .hero-pill,
        .story-badge,
        .mini-chip,
        .story-meta-pill,
        .story-action,
        .confidence-pill {{
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 700;
        }}

        .hero-pill {{
            padding: 8px 12px;
            background: rgba(255, 255, 255, 0.14);
            border: 1px solid rgba(255, 255, 255, 0.18);
        }}

        .hero-banner {{
            position: relative;
            z-index: 1;
            margin-top: 16px;
            padding: 10px 14px;
            border-radius: 16px;
            background: rgba(255, 255, 255, 0.12);
            border: 1px solid rgba(255, 255, 255, 0.18);
            font-size: 14px;
        }}

        .content {{
            padding: 28px 30px 36px;
        }}

        .overview-strip,
        .story-feed,
        .aggregate-section {{
            margin-top: 24px;
            animation: rise-in 0.55s ease both;
        }}

        .story-feed h2,
        .aggregate-section h2 {{
            margin: 0 0 10px;
            font-size: 26px;
            line-height: 1.15;
        }}

        .overview-strip {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 14px;
        }}

        .overview-card,
        .story-card,
        .aggregate-card {{
            animation: rise-in 0.6s ease both;
        }}

        .overview-card {{
            padding: 18px 18px 16px;
            border-radius: 20px;
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(250, 245, 238, 0.96));
            border: 1px solid var(--border);
        }}

        .overview-label {{
            font-size: 12px;
            color: var(--muted);
        }}

        .overview-value {{
            margin-top: 8px;
            font-size: 26px;
            font-weight: 800;
            line-height: 1.05;
        }}

        .overview-value.small {{
            font-size: 16px;
            line-height: 1.4;
        }}

        .story-list {{
            display: flex;
            flex-direction: column;
            gap: 22px;
            margin-top: 18px;
        }}

        .story-card {{
            padding: 24px;
            border-radius: 28px;
            background:
                linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(251, 247, 241, 0.94));
            border: 1px solid var(--border);
        }}

        .story-head {{
            display: grid;
            grid-template-columns: 72px minmax(0, 1fr);
            gap: 18px;
            align-items: start;
        }}

        .story-index {{
            width: 72px;
            height: 72px;
            border-radius: 22px;
            background: linear-gradient(180deg, var(--accent), var(--accent-deep));
            color: #fff;
            font-size: 26px;
            font-weight: 800;
            letter-spacing: -0.04em;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.12);
        }}

        .story-badges,
        .story-actions,
        .chip-row,
        .story-meta-row {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }}

        .story-title {{
            margin: 12px 0 10px;
            font-size: clamp(24px, 3vw, 34px);
            line-height: 1.18;
            letter-spacing: -0.03em;
        }}

        .story-summary {{
            margin: 0;
            max-width: 880px;
            font-size: 15px;
            color: #334052;
        }}

        .story-meta-row {{
            margin-top: 14px;
        }}

        .story-badge {{
            padding: 6px 10px;
        }}

        .story-badge.source {{
            background: #f2e9df;
            color: #5c4633;
        }}

        .story-badge.accent {{
            background: #fde7ab;
            color: #8f5600;
        }}

        .story-badge.muted {{
            background: #eef2f6;
            color: #5a6576;
        }}

        .story-meta-pill {{
            padding: 6px 10px;
            background: rgba(242, 233, 223, 0.78);
            color: #624f3e;
        }}

        .story-actions {{
            margin-top: 16px;
        }}

        .story-action {{
            padding: 8px 12px;
            text-decoration: none;
            background: var(--accent);
            color: #fff;
            transition: transform 0.18s ease, opacity 0.18s ease;
        }}

        .story-action:hover {{
            transform: translateY(-1px);
            opacity: 0.94;
        }}

        .story-action.secondary {{
            background: transparent;
            color: var(--accent-deep);
            border: 1px solid rgba(195, 91, 23, 0.18);
        }}

        .analysis-panel {{
            margin-top: 20px;
            padding: 20px 20px 18px;
            border-radius: 22px;
            background: linear-gradient(180deg, var(--panel) 0%, var(--panel-strong) 100%);
            border: 1px solid rgba(195, 91, 23, 0.10);
        }}

        .analysis-panel h3 {{
            margin: 8px 0 12px;
            font-size: 22px;
        }}

        .panel-subtitle {{
            margin: 14px 0 6px;
            font-size: 12px;
            font-weight: 800;
            letter-spacing: 0.05em;
            color: var(--muted);
            text-transform: uppercase;
        }}

        .panel-body {{
            margin: 0;
            color: #303a48;
            font-size: 14px;
        }}

        .panel-body.lead {{
            font-size: 15px;
            color: #1e2733;
        }}

        .panel-placeholder {{
            margin: 10px 0 0;
            color: var(--muted);
            font-size: 14px;
        }}

        .bullet-list {{
            margin: 0;
            padding-left: 18px;
            color: #303a48;
        }}

        .bullet-list li + li {{
            margin-top: 4px;
        }}

        .bullet-list.compact li + li {{
            margin-top: 2px;
        }}

        .confidence-pill {{
            margin-top: 14px;
            padding: 6px 10px;
            background: #e8f1fb;
            color: #25587a;
        }}

        .aggregate-head {{
            display: flex;
            justify-content: space-between;
            gap: 16px;
            align-items: flex-start;
            flex-wrap: wrap;
        }}

        .mini-chip {{
            padding: 5px 9px;
            background: var(--accent-soft);
            color: var(--accent-deep);
        }}

        .aggregate-grid {{
            margin-top: 18px;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 16px;
        }}

        .aggregate-card {{
            padding: 18px 18px 16px;
            border-radius: 22px;
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(251, 247, 241, 0.94));
            border: 1px solid var(--border);
        }}

        .aggregate-card h3 {{
            margin: 0 0 10px;
            font-size: 19px;
        }}

        .aggregate-card p {{
            margin: 0;
            color: #303a48;
            font-size: 14px;
        }}

        .aggregate-note {{
            margin: 8px 0 0;
            color: var(--muted);
        }}

        .empty-state {{
            padding: 52px 24px;
            text-align: center;
            color: var(--muted);
            font-size: 16px;
        }}

        .footer {{
            padding: 0 30px 30px;
            color: var(--muted);
            font-size: 13px;
        }}

        @keyframes rise-in {{
            from {{
                opacity: 0;
                transform: translateY(10px);
            }}
            to {{
                opacity: 1;
                transform: translateY(0);
            }}
        }}

        @media (max-width: 900px) {{
            .story-head {{
                grid-template-columns: 1fr;
            }}

            .story-index {{
                width: 60px;
                height: 60px;
                border-radius: 18px;
            }}
        }}

        @media (max-width: 720px) {{
            body {{
                padding: 14px;
            }}

            .hero {{
                padding: 30px 22px 24px;
            }}

            .content {{
                padding: 18px;
            }}

            .story-card {{
                padding: 18px;
                border-radius: 24px;
            }}

            .overview-strip {{
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }}

            .aggregate-grid {{
                grid-template-columns: 1fr;
            }}
        }}
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
                <span class="hero-pill">LLM Analysis：{view_model.analyzed_card_count}</span>
            </div>
            {version_html}
        </header>
        <main class="content">
            {sections_html}
        </main>
        <footer class="footer">NewsPulse HTML 报告 · 由 Stage 6 ReportPackage 直接渲染</footer>
    </div>
</body>
</html>"""
