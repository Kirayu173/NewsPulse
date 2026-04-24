# coding=utf-8
"""User-facing CLI error guidance helpers."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Iterable

from newspulse.core.config_paths import get_config_layout, resolve_frequency_words_path
from newspulse.workflow.shared.ai_runtime.errors import (
    AIConfigError,
    AIInvocationError,
    AIResponseDecodeError,
    PromptTemplateNotFoundError,
)


@dataclass(frozen=True)
class CLIErrorGuidance:
    """Structured user-facing guidance for a CLI failure."""

    title: str
    detail: str
    fixes: tuple[str, ...] = ()
    references: tuple[str, ...] = ()
    note: str = ""


def build_cli_error_guidance(exc: Exception) -> CLIErrorGuidance:
    """Map runtime exceptions to actionable CLI guidance."""

    if isinstance(exc, PromptTemplateNotFoundError):
        path = str(exc.details.get("path", "") or "").strip()
        return CLIErrorGuidance(
            title="AI prompt 文件缺失",
            detail=str(exc),
            fixes=(
                "检查 `config/` 下对应 prompt 文件是否存在。",
                "确认 `config/config.yaml` 中 selection/insight prompt 配置是否指向正确路径。",
                "可先运行 `newspulse doctor` 查看缺失项。",
            ),
            references=tuple(value for value in (path,) if value),
        )

    if isinstance(exc, AIConfigError):
        return CLIErrorGuidance(
            title="AI 配置不完整",
            detail=str(exc),
            fixes=(
                "检查仓库根目录 `.env` 中的 `AI_MODEL` / `AI_API_KEY` / `AI_BASE_URL`。",
                "如需固定接入方式，再补充 `AI_DRIVER`；如启用了 semantic recall，再检查 `AI_EMBEDDING_MODEL` / `AI_EMBEDDING_API_KEY` / `AI_EMBEDDING_BASE_URL`。",
                "运行 `newspulse doctor` 确认具体缺失项。",
            ),
        )

    if isinstance(exc, AIInvocationError):
        return CLIErrorGuidance(
            title="AI 调用失败",
            detail=str(exc),
            fixes=(
                "确认 `.env` 中生效的 `AI_MODEL`、`AI_API_KEY`、`AI_BASE_URL`、`AI_DRIVER` 彼此兼容。",
                "检查当前网络或代理设置是否可访问模型服务。",
                "如果只是偶发调用问题，可先重试或暂时切换到无需 AI 的配置。",
            ),
        )

    if isinstance(exc, AIResponseDecodeError):
        return CLIErrorGuidance(
            title="AI 响应解析失败",
            detail=str(exc),
            fixes=(
                "先确认当前模型是否适合输出结构化 JSON。",
                "检查对应 prompt 是否被意外改坏。",
                "必要时切回已验证过的模型或运行 `DEBUG=true python -m newspulse` 查看原始堆栈。",
            ),
        )

    if isinstance(exc, PermissionError):
        return CLIErrorGuidance(
            title="文件或目录权限不足",
            detail=str(exc),
            fixes=(
                "检查输出目录、日志文件路径或配置文件所在目录是否可写。",
                "如使用了自定义 `storage.local.data_dir`，请确认当前用户对该目录有写权限。",
            ),
        )

    if isinstance(exc, FileNotFoundError):
        layout = get_config_layout()
        config_path = str(layout.config_path)
        frequency_path = str(resolve_frequency_words_path(config_root=layout.config_root))
        references = _collect_existing_references(_extract_paths_from_message(str(exc)), [config_path, frequency_path])
        return CLIErrorGuidance(
            title="必需文件缺失",
            detail=str(exc),
            fixes=(
                "确认 `config/config.yaml` 与关键配置文件是否存在。",
                "如使用了自定义路径，请检查环境变量或配置中的文件路径是否正确。",
                "运行 `newspulse doctor` 查看完整缺失项。",
            ),
            references=tuple(references),
        )

    if isinstance(exc, ValueError):
        return CLIErrorGuidance(
            title="配置值非法",
            detail=str(exc),
            fixes=(
                "优先检查 `config/config.yaml` 与 `config/timeline.yaml` 的字段格式。",
                "如问题与调度有关，请重点检查时间段、preset、HH:MM 格式与重叠配置。",
                "运行 `newspulse doctor` 获取更细的配置校验结果。",
            ),
        )

    return CLIErrorGuidance(
        title="运行失败",
        detail=f"{type(exc).__name__}: {exc}",
        fixes=(
            "先运行 `newspulse doctor` 检查环境与配置。",
            "如需完整堆栈，请使用 `DEBUG=true python -m newspulse` 复现。",
        ),
    )


def print_cli_error(exc: Exception, *, stream=None) -> None:
    """Print user-facing guidance for a runtime exception."""

    target = stream or sys.stderr
    guidance = build_cli_error_guidance(exc)
    print(f"错误: {guidance.title}", file=target)
    print(f"原因: {guidance.detail}", file=target)
    if guidance.references:
        print("相关位置:", file=target)
        for reference in guidance.references:
            print(f"  - {reference}", file=target)
    if guidance.fixes:
        print("修复建议:", file=target)
        for index, fix in enumerate(guidance.fixes, start=1):
            print(f"  {index}. {fix}", file=target)
    if guidance.note:
        print(f"备注: {guidance.note}", file=target)


def _extract_paths_from_message(message: str) -> list[str]:
    values: list[str] = []
    for token in str(message or "").replace("'", " ").replace('"', " ").split():
        cleaned = token.strip(" ,.;:()[]{}")
        if "/" in cleaned or "\\" in cleaned:
            values.append(cleaned)
    return values


def _collect_existing_references(primary: Iterable[str], fallback: Iterable[str]) -> list[str]:
    results: list[str] = []
    for candidate in list(primary) + list(fallback):
        normalized = str(candidate or "").strip()
        if not normalized or normalized in results:
            continue
        results.append(normalized)
    return results
