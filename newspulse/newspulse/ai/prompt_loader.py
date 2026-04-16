# coding=utf-8
"""Load prompt templates from the project-owned config directory."""

from pathlib import Path
from typing import Optional, Tuple, Union

from newspulse.core.config_paths import resolve_prompt_path


def load_prompt_template(
    prompt_file: Union[str, Path],
    config_subdir: str = "",
    label: str = "AI",
    config_root: Optional[Union[str, Path]] = None,
) -> Tuple[str, str]:
    """Read a prompt file and split it into optional [system] / [user] parts."""
    prompt_path = resolve_prompt_path(
        str(prompt_file),
        config_root=config_root,
        config_subdir=config_subdir,
    )

    if not prompt_path.exists():
        print(f"[{label}] prompt file not found: {prompt_path}")
        return "", ""

    content = prompt_path.read_text(encoding="utf-8")

    system_prompt = ""
    user_prompt = ""

    if "[system]" in content and "[user]" in content:
        parts = content.split("[user]")
        system_part = parts[0]
        user_part = parts[1] if len(parts) > 1 else ""

        if "[system]" in system_part:
            system_prompt = system_part.split("[system]")[1].strip()

        user_prompt = user_part.strip()
    else:
        user_prompt = content

    return system_prompt, user_prompt
