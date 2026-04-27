# coding=utf-8
"""Keyword-selection frequency rule loading helpers."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional, Union

from newspulse.core.config_paths import DEFAULT_FREQUENCY_WORDS_FILE, resolve_frequency_words_path
from newspulse.utils.logging import get_logger
from newspulse.workflow.selection.models import KeywordRuleGroup, KeywordRuleSet, KeywordToken

logger = get_logger(__name__)


def _parse_token(word: str) -> KeywordToken:
    """Parse one configured keyword token."""

    display_name = ""
    word_config = word.strip()
    if "=>" in word_config:
        parts = re.split(r"\s*=>\s*", word_config, maxsplit=1)
        word_config = parts[0].strip()
        if len(parts) > 1 and parts[1].strip():
            display_name = parts[1].strip()

    regex_match = re.match(r"^/(.+)/[a-z]*$", word_config)
    if regex_match:
        pattern_str = regex_match.group(1)
        try:
            return KeywordToken(
                text=pattern_str,
                is_regex=True,
                pattern=re.compile(pattern_str, re.IGNORECASE),
                display_name=display_name,
            )
        except re.error as exc:
            logger.warning("Invalid regex pattern '/%s/': %s", pattern_str, exc)

    return KeywordToken(
        text=word_config,
        is_regex=False,
        pattern=None,
        display_name=display_name,
    )

def _word_matches(word_config: Union[str, dict, KeywordToken], title_lower: str) -> bool:
    """Return True when the configured token matches the lowercase title."""

    if isinstance(word_config, KeywordToken):
        if word_config.is_regex and word_config.pattern is not None:
            return bool(word_config.pattern.search(title_lower))
        return word_config.text.lower() in title_lower

    if isinstance(word_config, str):
        return word_config.lower() in title_lower

    if word_config.get("is_regex") and word_config.get("pattern"):
        return bool(word_config["pattern"].search(title_lower))
    return str(word_config.get("word", "")).lower() in title_lower


def load_keyword_rule_set(
    frequency_file: Optional[str] = None,
    config_root: Optional[Union[str, Path]] = None,
) -> KeywordRuleSet:
    """Load typed keyword-selection rules from the configured file."""

    frequency_path = resolve_frequency_words_path(
        frequency_file,
        config_root=config_root,
    )
    if not frequency_path.exists():
        missing_name = frequency_file or os.environ.get(
            "FREQUENCY_WORDS_PATH",
            DEFAULT_FREQUENCY_WORDS_FILE,
        )
        raise FileNotFoundError(f"frequency words file not found: {missing_name}")

    content = frequency_path.read_text(encoding="utf-8")
    blocks = [group.strip() for group in content.split("\n\n") if group.strip()]

    groups: list[KeywordRuleGroup] = []
    filter_tokens: list[KeywordToken] = []
    global_filters: list[str] = []
    current_section = "WORD_GROUPS"

    for block in blocks:
        lines = [
            line.strip()
            for line in block.split("\n")
            if line.strip() and not line.strip().startswith("#")
        ]
        if not lines:
            continue

        if lines[0].startswith("[") and lines[0].endswith("]"):
            section_name = lines[0][1:-1].upper()
            if section_name in ("GLOBAL_FILTER", "WORD_GROUPS"):
                current_section = section_name
                lines = lines[1:]

        if current_section == "GLOBAL_FILTER":
            for line in lines:
                if line.startswith(("!", "+", "@")):
                    continue
                if line:
                    global_filters.append(line)
            continue

        words = lines
        group_alias = None
        if words and words[0].startswith("[") and words[0].endswith("]"):
            potential_alias = words[0][1:-1].strip()
            if potential_alias.upper() not in ("GLOBAL_FILTER", "WORD_GROUPS"):
                group_alias = potential_alias
                words = words[1:]

        required_tokens: list[KeywordToken] = []
        normal_tokens: list[KeywordToken] = []
        max_items = 0

        for word in words:
            if word.startswith("@"):
                try:
                    count = int(word[1:])
                    if count > 0:
                        max_items = count
                except (TypeError, ValueError):
                    pass
                continue

            if word.startswith("!"):
                filter_tokens.append(_parse_token(word[1:]))
                continue

            if word.startswith("+"):
                required_tokens.append(_parse_token(word[1:]))
                continue

            normal_tokens.append(_parse_token(word))

        if not required_tokens and not normal_tokens:
            continue

        all_tokens = [*normal_tokens, *required_tokens]
        group_key = (
            " ".join(token.text for token in normal_tokens)
            if normal_tokens
            else " ".join(token.text for token in required_tokens)
        )

        label = group_alias or " / ".join(token.label for token in all_tokens) or group_key
        groups.append(
            KeywordRuleGroup(
                group_key=group_key,
                label=label,
                position=len(groups),
                max_items=max_items,
                required_tokens=tuple(required_tokens),
                normal_tokens=tuple(normal_tokens),
            )
        )

    return KeywordRuleSet(
        groups=tuple(groups),
        filter_tokens=tuple(filter_tokens),
        global_filters=tuple(global_filters),
        source_path=str(frequency_path),
    )
