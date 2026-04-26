# coding=utf-8
"""Render the simplified Chinese NewsPulse HTML report page."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Callable, Iterable, Optional

from newspulse.workflow.render.helpers import html_escape

if TYPE_CHECKING:
    from newspulse.workflow.render.models import (
        RenderInsightSectionView,
        RenderInsightSummaryView,
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


def _source_key(card: "RenderNewsCardView") -> str:
    return str(card.item.source_id or card.item.source_name or "unknown").strip().lower()


def _source_label(card: "RenderNewsCardView") -> str:
    return str(card.item.source_name or card.item.source_id or "未知来源")


def _clean_story_summary_text(text: str) -> str:
    normalized = " ".join(str(text or "").split())
    if not normalized:
        return ""

    topic_body = ""
    for prefix in ("主题:", "主题："):
        if normalized.startswith(prefix):
            topic_body = normalized[len(prefix) :].strip()
            break
    if not topic_body:
        return normalized

    topic_text = topic_body
    reason_text = ""
    for marker in ("| 入选原因:", "| 入选原因：", "｜ 入选原因:", "｜ 入选原因："):
        if marker in topic_body:
            topic_text, reason_text = topic_body.split(marker, 1)
            break
    if not reason_text:
        return normalized

    parts: list[str] = []
    topic_text = topic_text.strip(" |｜")
    reason_text = reason_text.strip()
    if topic_text:
        parts.append(f"聚焦 {topic_text}")
    if reason_text:
        parts.append(f"关键信号：{reason_text}")
    if not parts:
        return normalized
    rendered = "，".join(parts)
    if rendered[-1] not in "。.!?！？":
        rendered += "。"
    return rendered


def _story_summary_text(card: "RenderNewsCardView") -> str:
    raw_text = str(
        card.summary.summary or card.source_summary or card.item.summary or ""
    ).strip()
    return _clean_story_summary_text(raw_text)


def _search_text(card: "RenderNewsCardView") -> str:
    values = [
        card.item.title,
        card.item.source_name,
        card.item.source_id,
        _story_summary_text(card),
        card.item.summary,
        card.source_summary,
    ]
    return " ".join(str(value or "").strip() for value in values if str(value or "").strip())


def _render_badges(card: "RenderNewsCardView", *, show_new_section: bool) -> str:
    badges: list[str] = [
        (
            f'<button type="button" class="story-badge source js-source-filter" '
            f'data-source-key="{html_escape(_source_key(card))}" '
            f'aria-label="按来源筛选 {html_escape(_source_label(card))}">'
            f"{html_escape(_source_label(card))}"
            "</button>"
        )
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


def _render_story_summary(card: "RenderNewsCardView") -> str:
    summary_text = _story_summary_text(card)
    if not summary_text:
        return ""
    return f"""
        <div class="story-summary-block">
            <div class="story-summary-label">摘要</div>
            <p class="story-summary">{html_escape(summary_text)}</p>
        </div>
    """


def _render_story_card(card: "RenderNewsCardView", index: int, *, show_new_section: bool) -> str:
    return f"""
    <article
        class="story-card"
        id="story-{html_escape(card.item.news_item_id)}"
        data-story-card
        data-source-key="{html_escape(_source_key(card))}"
        data-search-text="{html_escape(_search_text(card))}"
    >
        <div class="story-head">
            <div class="story-index">{index:02d}</div>
            <div class="story-main">
                <div class="story-badges">{_render_badges(card, show_new_section=show_new_section)}</div>
                <h2 class="story-title">{html_escape(card.item.title)}</h2>
                {_render_story_summary(card)}
                <div class="story-meta-row">{_render_meta_row(card)}</div>
                <div class="story-actions">{_render_action_links(card)}</div>
            </div>
        </div>
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
    analyzed_count = sum(1 for card in cards if card.summary.visible)
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


def _render_filter_strip(cards: list["RenderNewsCardView"]) -> str:
    sources: list[tuple[str, str]] = []
    seen: set[str] = set()
    for card in cards:
        key = _source_key(card)
        if key in seen:
            continue
        seen.add(key)
        sources.append((key, _source_label(card)))

    source_buttons = "".join(
        (
            f'<button type="button" class="filter-chip" data-source-filter="{html_escape(key)}" '
            f'aria-pressed="false">{html_escape(label)}</button>'
        )
        for key, label in sources
    )
    return f"""
    <section class="control-strip">
        <div class="control-card control-card-search">
            <label class="control-label" for="story-search">搜索新闻</label>
            <div class="search-row">
                <input id="story-search" class="search-input" type="search" placeholder="输入标题、摘要或来源..." data-story-search>
                <button type="button" class="search-clear" data-clear-search>清空</button>
            </div>
        </div>
        <div class="control-card">
            <div class="control-label">来源过滤</div>
            <div class="filter-chip-row" data-filter-strip>
                <button type="button" class="filter-chip active" data-source-filter="all" aria-pressed="true">全部来源</button>
                {source_buttons}
            </div>
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
        {_render_filter_strip(cards)}
        <div class="story-empty" data-story-empty hidden>当前筛选条件下没有匹配的新闻卡片。</div>
        <div class="story-list">{stories}</div>
    </section>
    """


def _rendered_summary_cards(
    view_model: "RenderViewModel",
) -> list["RenderInsightSummaryView"]:
    cards = [summary for summary in view_model.summary_cards if summary.visible]
    return [summary for summary in cards if summary.kind == "report"][:1]


def _render_summary_card(summary) -> str:
    item_count = len(summary.item_ids)
    count_text = f"{item_count} 条新闻" if item_count else ""
    kind_text = "报告摘要"
    source_text = "、".join(summary.sources[:4])
    topic_text = "、".join(
        topic
        for topic in summary.evidence_topics[:4]
        if str(topic or "").strip() and str(topic).strip() != str(summary.title or "").strip()
    )
    meta_parts = [part for part in (topic_text, f"来源证据：{source_text}" if source_text else "") if part]
    meta_html = f'<div class="summary-meta-line">{html_escape(" · ".join(meta_parts))}</div>' if meta_parts else ""
    return f"""
    <article class="summary-card summary-{html_escape(summary.kind)}">
        <div class="summary-card-head">
            <span class="summary-kind">{html_escape(kind_text)}</span>
            <span class="summary-count">{html_escape(count_text)}</span>
        </div>
        <h3>{html_escape(summary.title or summary.key)}</h3>
        <p>{html_escape(summary.summary)}</p>
        {meta_html}
    </article>
    """


def _render_summary_section(view_model: "RenderViewModel") -> str:
    cards = _rendered_summary_cards(view_model)
    if not cards:
        return ""
    return f"""
    <section class="summary-section">
        <h2>摘要</h2>
        <div class="summary-list report-summary-list">{"".join(_render_summary_card(summary) for summary in cards)}</div>
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
    <section class="aggregate-section" data-collapsible-section>
        <div class="aggregate-head">
            <div class="aggregate-heading">
                <h2>全局洞察</h2>
                <div class="chip-row">{stats_html}</div>
            </div>
            <button
                type="button"
                class="section-toggle"
                data-toggle-target="aggregate-content"
                aria-expanded="true"
            >
                折叠
            </button>
        </div>
        <div class="aggregate-content" id="aggregate-content">
            <div class="aggregate-grid">{_render_insight_sections(insight.sections)}</div>
        </div>
    </section>
    """


def _page_styles() -> str:
    return """
        :root {
            color-scheme: light;
            --bg: #f4efe8;
            --paper: rgba(255, 252, 247, 0.96);
            --panel: #fff8f0;
            --panel-strong: #fff4e4;
            --ink: #17202d;
            --muted: #697383;
            --accent: #c35b17;
            --accent-deep: #8d3600;
            --accent-soft: #f6dcc4;
            --accent-ghost: rgba(195, 91, 23, 0.08);
            --border: rgba(195, 91, 23, 0.14);
            --shadow: 0 24px 70px rgba(59, 31, 8, 0.10);
        }

        * { box-sizing: border-box; }

        html { scroll-behavior: smooth; }

        body {
            margin: 0;
            padding: 22px;
            color: var(--ink);
            background:
                radial-gradient(circle at 10% 10%, rgba(195, 91, 23, 0.12), transparent 30%),
                radial-gradient(circle at 90% 18%, rgba(38, 91, 122, 0.08), transparent 26%),
                linear-gradient(180deg, #f8f3ec 0%, var(--bg) 100%);
            font-family: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
            line-height: 1.7;
        }

        button,
        input,
        textarea,
        select {
            font: inherit;
        }

        .shell {
            max-width: 1120px;
            margin: 0 auto;
            background: var(--paper);
            border: 1px solid var(--border);
            border-radius: 8px;
            overflow: hidden;
            box-shadow: var(--shadow);
            backdrop-filter: blur(12px);
        }

        .hero {
            position: relative;
            overflow: hidden;
            padding: 44px 38px 34px;
            background:
                radial-gradient(circle at top right, rgba(255, 255, 255, 0.18), transparent 30%),
                linear-gradient(135deg, rgba(195, 91, 23, 0.98), rgba(118, 52, 15, 0.94));
            color: #fff;
        }

        .hero::after {
            content: "";
            position: absolute;
            inset: auto -90px -110px auto;
            width: 260px;
            height: 260px;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.10);
            filter: blur(8px);
        }

        .hero h1 {
            position: relative;
            z-index: 1;
            margin: 0;
            font-size: clamp(30px, 5vw, 48px);
            line-height: 1.08;
            letter-spacing: -0.03em;
        }

        .hero-meta {
            position: relative;
            z-index: 1;
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 20px;
        }

        .hero-pill,
        .story-badge,
        .mini-chip,
        .story-meta-pill,
        .story-action,
        .filter-chip,
        .section-toggle {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 700;
        }

        .hero-pill {
            padding: 8px 12px;
            background: rgba(255, 255, 255, 0.14);
            border: 1px solid rgba(255, 255, 255, 0.18);
        }

        .hero-banner {
            position: relative;
            z-index: 1;
            margin-top: 16px;
            padding: 10px 14px;
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.12);
            border: 1px solid rgba(255, 255, 255, 0.18);
            font-size: 14px;
        }

        .content {
            padding: 28px 30px 36px;
        }

        .overview-strip,
        .story-feed,
        .summary-section,
        .aggregate-section {
            margin-top: 24px;
            animation: rise-in 0.55s ease both;
        }

        .story-feed h2,
        .summary-section h2,
        .aggregate-section h2 {
            margin: 0 0 10px;
            font-size: 24px;
            line-height: 1.15;
        }

        .overview-strip {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 14px;
        }

        .overview-card,
        .story-card,
        .summary-card,
        .aggregate-card,
        .control-card {
            animation: rise-in 0.6s ease both;
        }

        .overview-card {
            padding: 18px 18px 16px;
            border-radius: 8px;
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(250, 245, 238, 0.96));
            border: 1px solid var(--border);
        }

        .overview-label {
            font-size: 12px;
            color: var(--muted);
        }

        .overview-value {
            margin-top: 8px;
            font-size: 26px;
            font-weight: 800;
            line-height: 1.05;
        }

        .overview-value.small {
            font-size: 16px;
            line-height: 1.4;
        }

        .control-strip {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 14px;
            margin-top: 14px;
        }

        .control-card {
            padding: 18px;
            border-radius: 8px;
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(251, 247, 241, 0.90));
            border: 1px solid var(--border);
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.4);
        }

        .control-label {
            display: block;
            margin-bottom: 10px;
            color: var(--muted);
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 0.04em;
            text-transform: uppercase;
        }

        .search-row {
            display: flex;
            gap: 10px;
            align-items: center;
        }

        .search-input {
            flex: 1;
            min-width: 0;
            border-radius: 8px;
            border: 1px solid var(--border);
            background: rgba(255, 255, 255, 0.86);
            padding: 12px 14px;
            color: var(--ink);
            outline: none;
            transition: border-color 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;
        }

        .search-input:focus {
            border-color: rgba(195, 91, 23, 0.44);
            box-shadow: 0 0 0 4px rgba(195, 91, 23, 0.12);
            background: #fff;
        }

        .search-clear,
        .section-toggle,
        .filter-chip,
        .story-badge.source {
            border: 1px solid transparent;
            cursor: pointer;
            transition: transform 0.18s ease, opacity 0.18s ease, background 0.18s ease, border-color 0.18s ease, color 0.18s ease;
        }

        .search-clear {
            padding: 12px 14px;
            border-radius: 8px;
            background: var(--accent-ghost);
            color: var(--accent-deep);
            border-color: rgba(195, 91, 23, 0.12);
            white-space: nowrap;
        }

        .search-clear:hover,
        .search-clear:focus-visible,
        .section-toggle:hover,
        .section-toggle:focus-visible,
        .filter-chip:hover,
        .filter-chip:focus-visible,
        .story-badge.source:hover,
        .story-badge.source:focus-visible {
            transform: translateY(-1px);
            opacity: 0.96;
        }

        .filter-chip-row {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
        }

        .filter-chip {
            padding: 9px 14px;
            background: rgba(255, 255, 255, 0.82);
            color: #5c4633;
            border-color: rgba(195, 91, 23, 0.12);
        }

        .filter-chip.active {
            background: linear-gradient(180deg, var(--accent), var(--accent-deep));
            color: #fff;
            border-color: transparent;
        }

        .story-list {
            display: flex;
            flex-direction: column;
            gap: 22px;
            margin-top: 18px;
        }

        .story-card {
            padding: 22px;
            border-radius: 8px;
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(251, 247, 241, 0.94));
            border: 1px solid var(--border);
        }

        .story-card.is-hidden {
            display: none;
        }

        .story-head {
            display: grid;
            grid-template-columns: 58px minmax(0, 1fr);
            gap: 16px;
            align-items: start;
        }

        .story-index {
            width: 58px;
            height: 58px;
            border-radius: 8px;
            background: linear-gradient(180deg, var(--accent), var(--accent-deep));
            color: #fff;
            font-size: 22px;
            font-weight: 800;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.12);
        }

        .story-badges,
        .story-actions,
        .chip-row,
        .story-meta-row {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }

        .story-title {
            margin: 10px 0 12px;
            font-size: clamp(22px, 2.6vw, 30px);
            line-height: 1.24;
        }

        .story-summary-block {
            max-width: 900px;
            margin-top: 6px;
        }

        .story-summary-label {
            margin-bottom: 4px;
            color: var(--muted);
            font-size: 12px;
            font-weight: 800;
        }

        .story-summary {
            margin: 0;
            max-width: 880px;
            font-size: 16px;
            color: #334052;
            line-height: 1.75;
        }

        .story-meta-row {
            margin-top: 14px;
        }

        .story-badge {
            padding: 6px 10px;
        }

        .story-badge.source {
            background: #f2e9df;
            color: #5c4633;
        }

        .story-badge.accent {
            background: #fde7ab;
            color: #8f5600;
        }

        .story-badge.muted {
            background: #eef2f6;
            color: #5a6576;
        }

        .story-meta-pill {
            padding: 6px 10px;
            background: rgba(242, 233, 223, 0.78);
            color: #624f3e;
        }

        .story-actions {
            margin-top: 16px;
        }

        .story-action {
            padding: 8px 12px;
            text-decoration: none;
            background: var(--accent);
            color: #fff;
            transition: transform 0.18s ease, opacity 0.18s ease;
        }

        .story-action:hover {
            transform: translateY(-1px);
            opacity: 0.94;
        }

        .story-action.secondary {
            background: transparent;
            color: var(--accent-deep);
            border: 1px solid rgba(195, 91, 23, 0.18);
        }

        .story-empty,
        .empty-state {
            padding: 26px 24px;
            text-align: center;
            color: var(--muted);
            font-size: 15px;
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.75);
            border: 1px dashed rgba(195, 91, 23, 0.18);
        }

        .story-empty {
            margin-top: 18px;
        }

        .story-empty[hidden],
        .aggregate-content[hidden] {
            display: none;
        }

        .aggregate-head {
            display: flex;
            justify-content: space-between;
            gap: 16px;
            align-items: flex-start;
            flex-wrap: wrap;
        }

        .aggregate-heading {
            display: flex;
            flex-direction: column;
            gap: 10px;
        }

        .mini-chip {
            padding: 5px 9px;
            background: var(--accent-soft);
            color: var(--accent-deep);
        }

        .section-toggle {
            padding: 10px 14px;
            background: rgba(255, 255, 255, 0.86);
            color: var(--accent-deep);
            border-color: rgba(195, 91, 23, 0.14);
        }

        .aggregate-grid {
            margin-top: 18px;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 16px;
        }

        .aggregate-card {
            padding: 18px 18px 16px;
            border-radius: 8px;
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(251, 247, 241, 0.94));
            border: 1px solid var(--border);
        }

        .aggregate-card h3 {
            margin: 0 0 10px;
            font-size: 19px;
        }

        .aggregate-card p {
            margin: 0;
            color: #303a48;
            font-size: 14px;
        }

        .aggregate-note {
            margin: 8px 0 0;
            color: var(--muted);
        }

        .summary-list {
            display: flex;
            flex-direction: column;
            gap: 14px;
            margin-top: 14px;
        }

        .report-summary-list {
            margin-bottom: 18px;
        }

        .summary-subhead {
            margin: 16px 0 0;
            font-size: 18px;
        }

        .summary-card {
            padding: 18px;
            border-radius: 8px;
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(251, 247, 241, 0.94));
            border: 1px solid var(--border);
        }

        .summary-card-head {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            align-items: center;
        }

        .summary-kind,
        .summary-count {
            display: inline-flex;
            border-radius: 999px;
            padding: 4px 8px;
            font-size: 12px;
            font-weight: 700;
        }

        .summary-kind {
            background: #e8f1fb;
            color: #25587a;
        }

        .summary-count {
            background: rgba(242, 233, 223, 0.78);
            color: #624f3e;
        }

        .summary-card h3 {
            margin: 10px 0 6px;
            font-size: 20px;
        }

        .summary-card p {
            margin: 0;
            color: #303a48;
            font-size: 15px;
            line-height: 1.75;
        }

        .summary-meta-line {
            margin-top: 10px;
            color: var(--muted);
            font-size: 13px;
        }

        .footer {
            padding: 0 30px 30px;
            color: var(--muted);
            font-size: 13px;
        }

        @keyframes rise-in {
            from {
                opacity: 0;
                transform: translateY(10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        @media (prefers-color-scheme: dark) {
            :root {
                color-scheme: dark;
                --bg: #141a20;
                --paper: rgba(20, 25, 31, 0.92);
                --panel: #18202a;
                --panel-strong: #1d2833;
                --ink: #eef2f6;
                --muted: #aab3bf;
                --accent: #ff9d58;
                --accent-deep: #f07a2c;
                --accent-soft: rgba(255, 157, 88, 0.18);
                --accent-ghost: rgba(255, 157, 88, 0.10);
                --border: rgba(255, 157, 88, 0.16);
                --shadow: 0 24px 70px rgba(0, 0, 0, 0.32);
            }

            body {
                background:
                    radial-gradient(circle at 10% 10%, rgba(255, 157, 88, 0.08), transparent 28%),
                    radial-gradient(circle at 85% 12%, rgba(90, 163, 208, 0.10), transparent 25%),
                    linear-gradient(180deg, #10151b 0%, var(--bg) 100%);
            }

            .overview-card,
            .story-card,
            .summary-card,
            .aggregate-card,
            .control-card,
            .story-empty,
            .empty-state {
                background: linear-gradient(180deg, rgba(29, 36, 45, 0.96), rgba(20, 26, 34, 0.96));
            }

            .search-input,
            .section-toggle,
            .filter-chip,
            .search-clear {
                background: rgba(14, 19, 25, 0.86);
                color: var(--ink);
            }

            .story-badge.source,
            .story-meta-pill {
                background: rgba(255, 157, 88, 0.12);
                color: #ffd2b0;
            }

            .story-badge.muted {
                background: rgba(111, 130, 149, 0.18);
                color: #d3dce7;
            }

            .story-badge.accent {
                background: rgba(255, 218, 117, 0.16);
                color: #ffe29d;
            }

            .story-summary,
            .summary-card p,
            .aggregate-card p {
                color: #d6dee8;
            }
        }

        @media (max-width: 900px) {
            .story-head {
                grid-template-columns: 1fr;
            }

            .story-index {
                width: 60px;
                height: 60px;
                border-radius: 8px;
            }
        }

        @media (max-width: 720px) {
            body {
                padding: 14px;
            }

            .hero {
                padding: 30px 22px 24px;
            }

            .content {
                padding: 18px;
            }

            .story-card,
            .control-card {
                padding: 18px;
                border-radius: 8px;
            }

            .overview-strip {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }

            .aggregate-grid {
                grid-template-columns: 1fr;
            }

            .search-row {
                flex-direction: column;
                align-items: stretch;
            }

            .search-clear {
                width: 100%;
            }
        }
    """


def _page_script() -> str:
    return """
    (() => {
        const storyCards = Array.from(document.querySelectorAll('[data-story-card]'));
        const emptyState = document.querySelector('[data-story-empty]');
        const searchInput = document.querySelector('[data-story-search]');
        const clearSearchButton = document.querySelector('[data-clear-search]');
        const sourceButtons = Array.from(document.querySelectorAll('[data-source-filter]'));
        const inlineSourceButtons = Array.from(document.querySelectorAll('.js-source-filter'));
        const toggleButtons = Array.from(document.querySelectorAll('[data-toggle-target]'));

        let activeSource = 'all';

        const applyFilters = () => {
            const query = (searchInput?.value || '').trim().toLowerCase();
            let visibleCount = 0;

            storyCards.forEach((card) => {
                const searchText = (card.dataset.searchText || '').toLowerCase();
                const sourceKey = card.dataset.sourceKey || 'unknown';
                const matchesSource = activeSource === 'all' || sourceKey === activeSource;
                const matchesQuery = !query || searchText.includes(query);
                const visible = matchesSource && matchesQuery;
                card.classList.toggle('is-hidden', !visible);
                if (visible) {
                    visibleCount += 1;
                }
            });

            if (emptyState) {
                emptyState.hidden = visibleCount !== 0;
            }
        };

        const syncSourceButtons = () => {
            sourceButtons.forEach((button) => {
                const isActive = (button.dataset.sourceFilter || 'all') === activeSource;
                button.classList.toggle('active', isActive);
                button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
            });
        };

        const setActiveSource = (nextSource) => {
            activeSource = nextSource || 'all';
            syncSourceButtons();
            applyFilters();
        };

        if (searchInput) {
            searchInput.addEventListener('input', applyFilters);
            searchInput.addEventListener('keydown', (event) => {
                if (event.key === 'Escape') {
                    searchInput.value = '';
                    applyFilters();
                }
            });
        }

        if (clearSearchButton && searchInput) {
            clearSearchButton.addEventListener('click', () => {
                searchInput.value = '';
                searchInput.focus();
                applyFilters();
            });
        }

        sourceButtons.forEach((button) => {
            button.addEventListener('click', () => {
                const nextSource = button.dataset.sourceFilter || 'all';
                setActiveSource(nextSource == activeSource && nextSource !== 'all' ? 'all' : nextSource);
            });
        });

        inlineSourceButtons.forEach((button) => {
            button.addEventListener('click', () => {
                setActiveSource(button.dataset.sourceKey || 'all');
            });
        });

        toggleButtons.forEach((button) => {
            const targetId = button.dataset.toggleTarget;
            const target = targetId ? document.getElementById(targetId) : null;
            if (!target) {
                return;
            }
            button.addEventListener('click', () => {
                const expanded = button.getAttribute('aria-expanded') !== 'false';
                button.setAttribute('aria-expanded', expanded ? 'false' : 'true');
                target.hidden = expanded;
                button.textContent = expanded ? '展开' : '折叠';
            });
        });

        syncSourceButtons();
        applyFilters();
    })();
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
        if "insight" in region_order:
            summary_html = _render_summary_section(view_model)
            if summary_html:
                sections.append(summary_html)
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
