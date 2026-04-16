# coding=utf-8
"""Core exports."""

from newspulse.core.analyzer import calculate_news_weight, count_word_frequency, format_time_display
from newspulse.core.config import get_account_at_index, limit_accounts, parse_multi_account_config, validate_paired_configs
from newspulse.core.data import detect_latest_new_titles, detect_latest_new_titles_from_storage, read_all_today_titles, read_all_today_titles_from_storage
from newspulse.core.frequency import load_frequency_words, matches_word_groups
from newspulse.core.loader import load_config
from newspulse.core.scheduler import ResolvedSchedule, Scheduler

__all__ = [
    "parse_multi_account_config",
    "validate_paired_configs",
    "limit_accounts",
    "get_account_at_index",
    "load_config",
    "load_frequency_words",
    "matches_word_groups",
    "read_all_today_titles_from_storage",
    "read_all_today_titles",
    "detect_latest_new_titles_from_storage",
    "detect_latest_new_titles",
    "calculate_news_weight",
    "format_time_display",
    "count_word_frequency",
    "Scheduler",
    "ResolvedSchedule",
]
