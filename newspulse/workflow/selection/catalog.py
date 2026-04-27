# coding=utf-8
"""Structured topic-catalog helpers for the selection stage."""

from __future__ import annotations

import re
from typing import Sequence

from newspulse.workflow.selection.models import AIActiveTag, SelectionTopic

_TOPIC_HEADER = "[TOPIC_CATALOG]"
_PRIORITY_PATTERN = re.compile(r"^@(?:priority\s*[:=]\s*|)(\d+)\s*$", re.IGNORECASE)
_SOURCE_PATTERN = re.compile(r"^@source\s*[:=]\s*(.+)$", re.IGNORECASE)
_NUMBERED_TOPIC_PATTERN = re.compile(r"^\s*(\d+)[\.\)]\s*([^:：]+)\s*[:：]\s*(.+?)\s*$")


def parse_topic_catalog(interests_content: str) -> list[SelectionTopic]:
    """Parse structured selection topics from the interests file content."""

    content = str(interests_content or "").strip()
    if not content:
        return []

    structured_topics = _parse_structured_catalog(content)
    if structured_topics:
        return structured_topics
    return _parse_numbered_topics(content)


def build_runtime_topics(
    active_tags: Sequence[AIActiveTag],
    catalog_topics: Sequence[SelectionTopic],
) -> list[SelectionTopic]:
    """Merge active tag ids with the parsed topic catalog for runtime use."""

    if not active_tags:
        return []

    catalog_by_label = {topic.label: topic for topic in catalog_topics if topic.label}
    runtime_topics: list[SelectionTopic] = []
    for tag in active_tags:
        catalog_topic = catalog_by_label.get(tag.tag)
        if catalog_topic is None:
            runtime_topics.append(
                SelectionTopic(
                    topic_id=tag.id,
                    label=tag.tag,
                    description=tag.description,
                    priority=tag.priority,
                    source="ai_tag",
                )
            )
            continue

        runtime_topics.append(
            SelectionTopic(
                topic_id=tag.id,
                label=tag.tag,
                description=catalog_topic.description or tag.description,
                priority=tag.priority,
                seed_keywords=tuple(catalog_topic.seed_keywords),
                negative_keywords=tuple(catalog_topic.negative_keywords),
                source=catalog_topic.source or "catalog",
            )
        )
    return runtime_topics


def topics_to_tag_rows(topics: Sequence[SelectionTopic]) -> list[dict[str, object]]:
    """Convert parsed topics into persisted active-tag rows."""

    rows: list[dict[str, object]] = []
    for index, topic in enumerate(topics, start=1):
        label = str(topic.label or "").strip()
        if not label:
            continue
        rows.append(
            {
                "tag": label,
                "description": str(topic.description or "").strip(),
                "priority": int(topic.priority or index),
            }
        )
    return rows


def _parse_structured_catalog(content: str) -> list[SelectionTopic]:
    lines = content.splitlines()
    in_catalog = False
    sections: list[dict[str, object]] = []
    current: dict[str, object] | None = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if not in_catalog:
            if line.upper() == _TOPIC_HEADER:
                in_catalog = True
            continue

        if line.startswith("[") and line.endswith("]"):
            label = line[1:-1].strip()
            if not label:
                continue
            if current is not None:
                sections.append(current)
            current = {
                "label": label,
                "description_lines": [],
                "seed_keywords": [],
                "negative_keywords": [],
                "priority": 0,
                "source": "catalog",
            }
            continue

        if current is None:
            continue

        priority_match = _PRIORITY_PATTERN.match(line)
        if priority_match:
            current["priority"] = int(priority_match.group(1))
            continue

        source_match = _SOURCE_PATTERN.match(line)
        if source_match:
            current["source"] = source_match.group(1).strip() or "catalog"
            continue

        if line.startswith("+"):
            keyword = line[1:].strip()
            if keyword:
                current["seed_keywords"].append(keyword)
            continue

        if line.startswith("-"):
            keyword = line[1:].strip()
            if keyword:
                current["negative_keywords"].append(keyword)
            continue

        current["description_lines"].append(line)

    if current is not None:
        sections.append(current)

    topics: list[SelectionTopic] = []
    for fallback_priority, section in enumerate(sections, start=1):
        label = str(section.get("label", "")).strip()
        if not label:
            continue
        priority = int(section.get("priority", 0) or fallback_priority)
        topics.append(
            SelectionTopic(
                topic_id=0,
                label=label,
                description=" ".join(str(line).strip() for line in section.get("description_lines", []) if str(line).strip()),
                priority=priority,
                seed_keywords=tuple(
                    keyword for keyword in section.get("seed_keywords", []) if str(keyword).strip()
                ),
                negative_keywords=tuple(
                    keyword for keyword in section.get("negative_keywords", []) if str(keyword).strip()
                ),
                source=str(section.get("source", "catalog") or "catalog"),
            )
        )

    topics.sort(key=lambda topic: (topic.priority, topic.label.lower()))
    return topics


def _parse_numbered_topics(content: str) -> list[SelectionTopic]:
    topics: list[SelectionTopic] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _NUMBERED_TOPIC_PATTERN.match(line)
        if not match:
            continue
        topics.append(
            SelectionTopic(
                topic_id=0,
                label=match.group(2).strip(),
                description=match.group(3).strip(),
                priority=int(match.group(1)),
                source="interests_outline",
            )
        )
    topics.sort(key=lambda topic: (topic.priority, topic.label.lower()))
    return topics
