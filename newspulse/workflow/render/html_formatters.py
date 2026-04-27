# coding=utf-8
"""Formatting helpers for the card-first HTML report."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from newspulse.workflow.render.models import RenderNewsCardView

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

