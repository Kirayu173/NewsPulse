# coding=utf-8
"""HTML component renderers for the card-first report page."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Iterable

from newspulse.workflow.render.helpers import html_escape
from newspulse.workflow.render.html_formatters import (
    _mode_label,
    _rank_text,
    _rank_timeline_text,
    _search_text,
    _source_key,
    _source_label,
    _story_summary_text,
)

if TYPE_CHECKING:
    from newspulse.workflow.render.models import (
        RenderInsightSectionView,
        RenderInsightSummaryView,
        RenderInsightView,
        RenderNewsCardView,
        RenderViewModel,
    )

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
    if insight.status in {"fallback", "partial"}:
        stats_bits.append(insight.status)
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

