# coding=utf-8
"""Shared scoring helpers used by workflow stages."""

from __future__ import annotations


def calculate_news_weight(
    title_data: dict,
    rank_threshold: int,
    weight_config: dict,
) -> float:
    """Calculate the hotlist weight used for selection and render ordering."""

    ranks = title_data.get("ranks", [])
    if not ranks:
        return 0.0

    count = title_data.get("count", len(ranks))

    rank_score_sum = 0
    high_rank_count = 0
    for rank in ranks:
        rank_score_sum += 11 - min(rank, 10)
        if rank <= rank_threshold:
            high_rank_count += 1

    rank_weight = (rank_score_sum / len(ranks)) * 10
    frequency_weight = min(count, 10) * 10
    hotness_ratio = high_rank_count / len(ranks)
    hotness_weight = hotness_ratio * 100

    return (
        rank_weight * weight_config["RANK_WEIGHT"]
        + frequency_weight * weight_config["FREQUENCY_WEIGHT"]
        + hotness_weight * weight_config["HOTNESS_WEIGHT"]
    )


__all__ = ["calculate_news_weight"]
