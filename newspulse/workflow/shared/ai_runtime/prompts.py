# coding=utf-8
"""Prompt template loading helpers for the shared workflow runtime."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from newspulse.core.config_paths import resolve_prompt_path
from newspulse.workflow.shared.ai_runtime.errors import PromptTemplateNotFoundError


@dataclass(frozen=True)
class PromptTemplate:
    """Prompt template with optional system and user sections."""

    path: Path
    system_prompt: str = ""
    user_prompt: str = ""

    @property
    def is_empty(self) -> bool:
        """Return whether both prompt sections are empty."""

        return not self.system_prompt and not self.user_prompt

    def build_messages(self, user_prompt: Optional[str] = None) -> list[dict[str, str]]:
        """Build chat messages from the template."""

        messages: list[dict[str, str]] = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        final_user_prompt = self.user_prompt if user_prompt is None else user_prompt
        if final_user_prompt:
            messages.append({"role": "user", "content": final_user_prompt})
        return messages


def split_prompt_sections(content: str) -> tuple[str, str]:
    """Split prompt content into optional system/user sections."""

    normalized = content.lstrip("\ufeff")
    system_marker = "[system]"
    user_marker = "[user]"
    system_index = normalized.find(system_marker)
    user_index = normalized.find(user_marker)

    if system_index >= 0 and user_index >= 0:
        if system_index < user_index:
            system_prompt = normalized[system_index + len(system_marker):user_index].strip()
            user_prompt = normalized[user_index + len(user_marker):].strip()
            return system_prompt, user_prompt

        user_prompt = normalized[user_index + len(user_marker):system_index].strip()
        system_prompt = normalized[system_index + len(system_marker):].strip()
        return system_prompt, user_prompt

    if user_index >= 0:
        return "", normalized[user_index + len(user_marker):].strip()

    if system_index >= 0:
        return normalized[system_index + len(system_marker):].strip(), ""

    return "", normalized.strip()


def load_prompt_template(
    prompt_file: Union[str, Path],
    *,
    config_root: Optional[Union[str, Path]] = None,
    config_subdir: str = "",
    required: bool = False,
) -> PromptTemplate:
    """Load a prompt template from the project-owned config directory."""

    prompt_path = resolve_prompt_path(
        str(prompt_file),
        config_root=config_root,
        config_subdir=config_subdir,
    )
    if not prompt_path.exists():
        if required:
            raise PromptTemplateNotFoundError(
                "Prompt template file not found",
                details={"path": str(prompt_path)},
            )
        return PromptTemplate(path=prompt_path)

    content = prompt_path.read_text(encoding="utf-8")
    system_prompt, user_prompt = split_prompt_sections(content)
    return PromptTemplate(
        path=prompt_path,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )
