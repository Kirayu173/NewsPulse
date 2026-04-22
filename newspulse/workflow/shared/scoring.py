# coding=utf-8
"""Shared scoring helpers used by workflow stages."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

DEFAULT_WEIGHT_CONFIG = {
    "RANK_WEIGHT": 0.6,
    "FREQUENCY_WEIGHT": 0.3,
    "HOTNESS_WEIGHT": 0.1,
}


def calculate_news_weight(
    title_data: Mapping[str, Any],
    rank_threshold: int,
    weight_config: Mapping[str, Any] | None,
) -> float:
    """Calculate the render weight used for platform sorting."""

    ranks = _normalize_ranks(title_data)
    if not ranks:
        return 0.0

    threshold = max(1, int(rank_threshold or 1))
    weights = _normalize_weight_config(weight_config)
    count = _normalize_count(title_data, fallback=len(ranks))

    rank_score = sum(max(1, 11 - min(rank, 10)) for rank in ranks) / len(ranks)
    frequency_score = min(count, 10)
    hotness_score = sum(1 for rank in ranks if rank <= threshold) / len(ranks)

    return (
        rank_score * 10 * weights["RANK_WEIGHT"]
        + frequency_score * 10 * weights["FREQUENCY_WEIGHT"]
        + hotness_score * 100 * weights["HOTNESS_WEIGHT"]
    )



def _normalize_ranks(title_data: Mapping[str, Any]) -> list[int]:
    ranks = title_data.get("ranks", [])
    normalized: list[int] = []
    if isinstance(ranks, Sequence) and not isinstance(ranks, (str, bytes)):
        for rank in ranks:
            parsed = _coerce_positive_int(rank)
            if parsed is not None:
                normalized.append(parsed)
    if not normalized:
        fallback_rank = _coerce_positive_int(title_data.get("rank"))
        if fallback_rank is not None:
            normalized.append(fallback_rank)
    return sorted(set(normalized))



def _normalize_count(title_data: Mapping[str, Any], *, fallback: int) -> int:
    count = _coerce_positive_int(title_data.get("count"))
    return count if count is not None else max(1, fallback)



def _normalize_weight_config(weight_config: Mapping[str, Any] | None) -> dict[str, float]:
    normalized = dict(DEFAULT_WEIGHT_CONFIG)
    if not isinstance(weight_config, Mapping):
        return normalized
    for key in DEFAULT_WEIGHT_CONFIG:
        try:
            normalized[key] = float(weight_config.get(key, normalized[key]))
        except (TypeError, ValueError):
            continue
    return normalized



def _coerce_positive_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


__all__ = ["DEFAULT_WEIGHT_CONFIG", "calculate_news_weight"]
