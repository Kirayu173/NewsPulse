# coding=utf-8
"""Aggregate lightweight insight briefs into stable insight sections."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from newspulse.workflow.insight.models import (
    DEFAULT_SECTION_TEMPLATES,
    InsightBrief,
    InsightNewsContext,
    InsightSectionTemplate,
    build_summary,
    resolve_section_title,
)
from newspulse.workflow.shared.ai_runtime.client import AIRuntimeClient
from newspulse.workflow.shared.ai_runtime.codec import extract_json_block
from newspulse.workflow.shared.ai_runtime.errors import AIResponseDecodeError
from newspulse.workflow.shared.ai_runtime.prompts import PromptTemplate, load_prompt_template
from newspulse.workflow.shared.ai_runtime.request_config import build_request_overrides
from newspulse.workflow.shared.contracts import InsightSection


class InsightAggregateGenerator:
    """Generate stable aggregate insight sections from lightweight briefs."""

    def __init__(
        self,
        *,
        ai_runtime_config: Mapping[str, Any] | None = None,
        analysis_config: Mapping[str, Any] | None = None,
        config_root: str | Path | None = None,
        client: AIRuntimeClient | Any | None = None,
        prompt_template: PromptTemplate | None = None,
        section_templates: tuple[InsightSectionTemplate, ...] = DEFAULT_SECTION_TEMPLATES,
        request_overrides: Mapping[str, Any] | None = None,
    ):
        self.analysis_config = dict(analysis_config or {})
        self.config_root = Path(config_root) if config_root is not None else None
        self.section_templates = section_templates
        if client is None:
            if ai_runtime_config is None:
                raise ValueError("AI runtime config is required when no client is provided")
            client = AIRuntimeClient(ai_runtime_config)
        self.client = client
        self.prompt_template = prompt_template or load_prompt_template(
            self.analysis_config.get("PROMPT_FILE", "ai_analysis_prompt.txt"),
            config_root=self.config_root,
            required=True,
        )
        self.request_overrides = build_request_overrides(
            self.analysis_config,
            prompt_template=self.prompt_template,
            operation="insight",
            prompt_name="aggregate",
            overrides=request_overrides,
        )

    def generate(
        self,
        briefs: Sequence[InsightBrief],
        contexts: Sequence[InsightNewsContext],
    ) -> tuple[list[InsightSection], str, dict[str, Any]]:
        valid_briefs = [brief for brief in briefs if str(brief.news_item_id or "").strip() and str(brief.title or "").strip()]
        if not valid_briefs:
            return [], "", {"skipped": True, "reason": "no briefs available"}

        brief_payload = _build_brief_payload(valid_briefs)
        source_distribution = _source_distribution(valid_briefs, contexts)
        topic_distribution = _topic_distribution(valid_briefs, contexts)
        user_prompt = self._render_prompt(brief_payload, source_distribution, topic_distribution)
        raw_response = ""
        try:
            response = self.client.generate_json(
                self.prompt_template.build_messages(user_prompt),
                **self.request_overrides,
            )
            raw_response = response.text
            payload = response.json_payload
            sections = _coerce_sections(
                payload,
                brief_payload=brief_payload,
                section_templates=self.section_templates,
                source_distribution=source_distribution,
                topic_distribution=topic_distribution,
            )
            return sections, raw_response, {
                "brief_count": len(valid_briefs),
                "source_distribution": source_distribution,
                "topic_distribution": topic_distribution,
                "section_count": len(sections),
            }
        except Exception as exc:
            fallback = _fallback_section(valid_briefs, source_distribution, topic_distribution)
            return fallback, raw_response, {
                "brief_count": len(valid_briefs),
                "source_distribution": source_distribution,
                "topic_distribution": topic_distribution,
                "section_count": len(fallback),
                "error": f"{type(exc).__name__}: {exc}",
                "raw_preview": extract_json_block(raw_response)[:500],
            }

    def _render_prompt(
        self,
        brief_payload: list[dict[str, Any]],
        source_distribution: dict[str, int],
        topic_distribution: dict[str, int],
    ) -> str:
        user_prompt = self.prompt_template.user_prompt
        replacements = {
            "news_count": str(len(brief_payload)),
            "briefs_json": json.dumps(brief_payload, ensure_ascii=False, indent=2),
            "source_distribution_json": json.dumps(source_distribution, ensure_ascii=False, indent=2),
            "topic_distribution_json": json.dumps(topic_distribution, ensure_ascii=False, indent=2),
            "language": str(self.analysis_config.get("LANGUAGE", "Chinese") or "Chinese"),
        }
        for key, value in replacements.items():
            user_prompt = user_prompt.replace("{" + key + "}", str(value))
        return user_prompt


def _build_brief_payload(briefs: Sequence[InsightBrief]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for brief in briefs:
        payload.append(
            {
                "news_item_id": brief.news_item_id,
                "title": brief.title,
                "source_id": brief.source_id,
                "source_name": brief.source_name,
                "source_kind": brief.source_kind,
                "summary": brief.summary,
                "attributes": list(brief.attributes),
                "matched_topics": list(brief.matched_topics),
                "llm_reasons": list(brief.llm_reasons),
                "semantic_score": brief.semantic_score,
                "quality_score": brief.quality_score,
                "current_rank": brief.current_rank,
                "rank_trend": brief.rank_trend,
                "url": brief.url,
            }
        )
    return payload


def _source_distribution(briefs: Sequence[InsightBrief], contexts: Sequence[InsightNewsContext]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for brief in briefs:
        counter.update([brief.source_name or brief.source_id or "unknown"])
    if counter:
        return dict(counter)
    for context in contexts:
        counter.update([context.source_name or context.source_id or "unknown"])
    return dict(counter)


def _topic_distribution(briefs: Sequence[InsightBrief], contexts: Sequence[InsightNewsContext]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for brief in briefs:
        counter.update(brief.matched_topics)
    if counter:
        return dict(counter)
    for context in contexts:
        counter.update(context.selection_evidence.matched_topics)
    return dict(counter)


def _coerce_sections(
    payload: Any,
    *,
    brief_payload: Sequence[dict[str, Any]],
    section_templates: Sequence[InsightSectionTemplate],
    source_distribution: dict[str, int],
    topic_distribution: dict[str, int],
) -> list[InsightSection]:
    if isinstance(payload, Mapping) and isinstance(payload.get("sections"), list):
        sections: list[InsightSection] = []
        seen_keys: set[str] = set()
        for row in payload.get("sections", []):
            if not isinstance(row, Mapping):
                continue
            key = str(row.get("key", "") or "").strip()
            content = str(row.get("content", "") or "").strip()
            if not key or not content or key in seen_keys:
                continue
            supporting_news_ids = _coerce_id_list(row.get("supporting_news_ids"))
            supporting_topics = _coerce_text_list(row.get("supporting_topics"))
            sections.append(
                InsightSection(
                    key=key,
                    title=resolve_section_title(key, fallback=str(row.get("title", key) or key)),
                    content=content,
                    summary=str(row.get("summary", "") or build_summary(content)).strip(),
                    metadata={
                        "supporting_news_ids": supporting_news_ids or _default_supporting_news_ids(brief_payload),
                        "supporting_topics": supporting_topics or list(topic_distribution)[:6],
                        "source_distribution": _coerce_distribution(row.get("source_distribution")) or source_distribution,
                        "section_generator": "aggregate_llm",
                    },
                )
            )
            seen_keys.add(key)
        if sections:
            return sections

    if not isinstance(payload, Mapping):
        raise AIResponseDecodeError("aggregate insight payload must be a JSON object")

    sections: list[InsightSection] = []
    for template in section_templates:
        raw_value = payload.get(template.field_name)
        content = ""
        supporting_news_ids: list[str] = []
        supporting_topics: list[str] = []
        section_source_distribution: dict[str, int] = source_distribution
        if isinstance(raw_value, Mapping):
            content = str(raw_value.get("content", "") or "").strip()
            supporting_news_ids = _coerce_id_list(raw_value.get("supporting_news_ids"))
            supporting_topics = _coerce_text_list(raw_value.get("supporting_topics"))
            section_source_distribution = _coerce_distribution(raw_value.get("source_distribution")) or source_distribution
        else:
            content = str(raw_value or "").strip()
        if not content:
            continue
        sections.append(
            InsightSection(
                key=template.key,
                title=template.title,
                content=content,
                summary=build_summary(content, template.summary_limit),
                metadata={
                    "supporting_news_ids": supporting_news_ids or _default_supporting_news_ids(brief_payload),
                    "supporting_topics": supporting_topics or list(topic_distribution)[:6],
                    "source_distribution": section_source_distribution,
                    "section_generator": "aggregate_llm",
                },
            )
        )
    if not sections:
        raise AIResponseDecodeError("aggregate insight payload did not contain any section content")
    return sections


def _fallback_section(
    briefs: Sequence[InsightBrief],
    source_distribution: Mapping[str, int],
    topic_distribution: Mapping[str, int],
) -> list[InsightSection]:
    first = briefs[0]
    content = first.summary or first.title
    if first.matched_topics:
        content = f"{content} ????????? {', '.join(first.matched_topics[:3])}?"
    elif first.source_name:
        content = f"{content} ???????? {first.source_name} ????"
    return [
        InsightSection(
            key="core_trends",
            title=resolve_section_title("core_trends"),
            content=content.strip() or "No aggregate insight could be generated.",
            summary=build_summary(content),
            metadata={
                "supporting_news_ids": [brief.news_item_id for brief in briefs[:4]],
                "supporting_topics": list(topic_distribution)[:6],
                "source_distribution": dict(source_distribution),
                "section_generator": "aggregate_fallback",
            },
        )
    ]


def _default_supporting_news_ids(brief_payload: Sequence[dict[str, Any]]) -> list[str]:
    return [str(row.get("news_item_id", "")).strip() for row in brief_payload[:4] if str(row.get("news_item_id", "")).strip()]


def _coerce_id_list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, Sequence):
        return []
    result: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result[:8]


def _coerce_text_list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, Sequence):
        return []
    result: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result[:8]


def _coerce_distribution(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    payload: dict[str, int] = {}
    for key, raw in value.items():
        name = str(key or "").strip()
        if not name:
            continue
        try:
            count = int(raw or 0)
        except (TypeError, ValueError):
            continue
        if count > 0:
            payload[name] = count
    return payload
