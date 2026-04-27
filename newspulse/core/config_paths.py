from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

PathLike = Union[str, os.PathLike[str]]

DEFAULT_CONFIG_FILE = "config.yaml"
DEFAULT_TIMELINE_FILE = "timeline.yaml"
DEFAULT_FREQUENCY_WORDS_FILE = "rules/keyword/default.txt"
DEFAULT_AI_INTERESTS_FILE = "profiles/ai/default.txt"
DEFAULT_SELECTION_PROMPT_FILE = "prompts/selection/classify.txt"
DEFAULT_SELECTION_EXTRACT_PROMPT_FILE = "prompts/selection/extract_tags.txt"
DEFAULT_SELECTION_UPDATE_TAGS_PROMPT_FILE = "prompts/selection/update_tags.txt"
DEFAULT_GLOBAL_INSIGHT_PROMPT_FILE = "prompts/insight/global_insight.txt"
DEFAULT_ITEM_SUMMARY_PROMPT_FILE = "prompts/insight/item_summary_batch.txt"
DEFAULT_REPORT_SUMMARY_PROMPT_FILE = "prompts/insight/report_summary.txt"


@dataclass(frozen=True)
class ConfigLayout:
    project_root: Path
    config_root: Path
    config_path: Path


def get_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def get_default_config_root() -> Path:
    return get_project_root() / "config"


def _to_path(path_value: PathLike) -> Path:
    return Path(path_value).expanduser()


def _is_project_config_reference(path: Path) -> bool:
    return bool(path.parts) and path.parts[0] == "config"


def resolve_project_path(path_value: PathLike) -> Path:
    path = _to_path(path_value)
    if path.is_absolute():
        return path
    return get_project_root() / path


def get_config_layout(config_path: Optional[PathLike] = None) -> ConfigLayout:
    raw_config_path = config_path or os.environ.get("CONFIG_PATH", "")
    resolved_config_path = (
        resolve_project_path(raw_config_path)
        if raw_config_path
        else get_default_config_root() / DEFAULT_CONFIG_FILE
    )

    return ConfigLayout(
        project_root=get_project_root(),
        config_root=resolved_config_path.parent,
        config_path=resolved_config_path,
    )


def resolve_config_resource(
    path_value: PathLike,
    *,
    config_root: Optional[PathLike] = None,
    config_subdir: str = "",
) -> Path:
    path = _to_path(path_value)
    if path.is_absolute():
        return path
    if _is_project_config_reference(path):
        return get_project_root() / path

    root = _to_path(config_root) if config_root is not None else get_default_config_root()
    if config_subdir:
        subdir = Path(config_subdir)
        if tuple(path.parts[: len(subdir.parts)]) == tuple(subdir.parts):
            return root / path
        return root / subdir / path
    return root / path


def resolve_timeline_path(*, config_root: Optional[PathLike] = None) -> Path:
    root = _to_path(config_root) if config_root is not None else get_default_config_root()
    return root / DEFAULT_TIMELINE_FILE


def resolve_frequency_words_path(
    frequency_file: Optional[str] = None,
    *,
    config_root: Optional[PathLike] = None,
) -> Path:
    root = _to_path(config_root) if config_root is not None else get_default_config_root()
    raw_value = frequency_file or os.environ.get("FREQUENCY_WORDS_PATH", "")
    if not raw_value:
        return root / DEFAULT_FREQUENCY_WORDS_FILE

    path = _to_path(raw_value)
    if path.is_absolute():
        return path
    if len(path.parts) > 1 or _is_project_config_reference(path):
        return resolve_config_resource(path, config_root=root)
    if path.name == Path(DEFAULT_FREQUENCY_WORDS_FILE).name:
        return root / DEFAULT_FREQUENCY_WORDS_FILE
    return root / "rules" / "keyword" / path.name


def resolve_ai_interests_path(
    interests_file: Optional[str] = None,
    *,
    config_root: Optional[PathLike] = None,
) -> Path:
    root = _to_path(config_root) if config_root is not None else get_default_config_root()
    if not interests_file:
        return root / DEFAULT_AI_INTERESTS_FILE

    path = _to_path(interests_file)
    if path.is_absolute():
        return path
    if len(path.parts) > 1 or _is_project_config_reference(path):
        return resolve_config_resource(path, config_root=root)
    if path.name == Path(DEFAULT_AI_INTERESTS_FILE).name:
        return root / DEFAULT_AI_INTERESTS_FILE
    return root / "profiles" / "ai" / path.name


def resolve_prompt_path(
    prompt_file: str,
    *,
    config_root: Optional[PathLike] = None,
    config_subdir: str = "",
) -> Path:
    return resolve_config_resource(
        prompt_file,
        config_root=config_root,
        config_subdir=config_subdir,
    )
