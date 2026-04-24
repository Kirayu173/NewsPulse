# coding=utf-8
"""Basic parsing helpers shared by workflow AI stages."""

from __future__ import annotations

import json
from typing import Any

from newspulse.workflow.shared.ai_runtime.errors import AIResponseDecodeError


def coerce_text_content(content: Any) -> str:
    """Normalize provider message content into a plain text string."""

    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        normalized: list[str] = []
        for item in content:
            if isinstance(item, dict):
                normalized.append(str(item.get("text", item.get("content", item))))
            else:
                normalized.append(str(getattr(item, "text", item)))
        return "\n".join(part for part in normalized if part)
    if hasattr(content, "text"):
        return str(getattr(content, "text", "") or "")
    return str(content)


def extract_json_block(response_text: Any) -> str:
    """Extract the most likely JSON block from a raw AI response."""

    if hasattr(response_text, "text") and not isinstance(response_text, str):
        response_text = getattr(response_text, "text", "")
    text = (str(response_text or "")).strip()
    if not text:
        return ""

    fence_markers = ("```json", "```JSON", "```")
    for marker in fence_markers:
        start = text.find(marker)
        if start >= 0:
            tail = text[start + len(marker):]
            end = tail.find("```")
            if end >= 0:
                candidate = tail[:end].strip()
                if candidate:
                    return candidate

    first_object = text.find("{")
    last_object = text.rfind("}")
    first_array = text.find("[")
    last_array = text.rfind("]")

    candidates: list[tuple[int, int]] = []
    if first_object >= 0 and last_object > first_object:
        candidates.append((first_object, last_object + 1))
    if first_array >= 0 and last_array > first_array:
        candidates.append((first_array, last_array + 1))

    if not candidates:
        return text

    start, end = min(candidates, key=lambda item: item[0])
    return text[start:end].strip()


def decode_json_response(response_text: Any, *, repair: bool = True) -> Any:
    """Decode structured JSON data from a raw AI response or AI result."""

    if hasattr(response_text, "json_payload") and getattr(response_text, "json_payload") is not None:
        return getattr(response_text, "json_payload")
    if isinstance(response_text, (dict, list)):
        return response_text
    if hasattr(response_text, "text") and not isinstance(response_text, str):
        response_text = getattr(response_text, "text", "")
    if not isinstance(response_text, str):
        raise AIResponseDecodeError(
            "AI response is not JSON-decodable text",
            details={"type": type(response_text).__name__},
        )

    candidate = extract_json_block(response_text)
    if not candidate:
        raise AIResponseDecodeError("AI response does not contain JSON")

    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        if repair:
            try:
                from json_repair import repair_json

                repaired = repair_json(candidate, return_objects=True)
                if repaired is not None:
                    return repaired
            except Exception:
                pass

        raise AIResponseDecodeError(
            "Failed to decode AI JSON response",
            details={"error": str(exc), "candidate": candidate[:200]},
        ) from exc
