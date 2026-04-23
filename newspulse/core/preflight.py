# coding=utf-8
"""Shared startup and doctor preflight checks."""

from __future__ import annotations

import sys
import tomllib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal

from newspulse import __version__
from newspulse.context import AppContext
from newspulse.core.config_paths import (
    get_config_layout,
    resolve_ai_interests_path,
    resolve_frequency_words_path,
    resolve_timeline_path,
)
from newspulse.core.loader import load_config
from newspulse.workflow.shared.ai_runtime.client import AIRuntimeClient
from newspulse.workflow.shared.ai_runtime.embedding import EmbeddingRuntimeConfig
from newspulse.workflow.shared.ai_runtime.errors import AIConfigError

CheckStatus = Literal["pass", "warn", "fail", "skip"]


@dataclass(frozen=True)
class PreflightCheckResult:
    """One startup or doctor check result."""

    status: CheckStatus
    item: str
    detail: str
    hint: str = ""


@dataclass
class PreflightReport:
    """Structured preflight report shared by startup and doctor."""

    mode: str
    config_path: str
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    checks: list[PreflightCheckResult] = field(default_factory=list)
    config: dict[str, Any] | None = None

    @property
    def pass_count(self) -> int:
        return sum(1 for check in self.checks if check.status == "pass")

    @property
    def warn_count(self) -> int:
        return sum(1 for check in self.checks if check.status == "warn")

    @property
    def fail_count(self) -> int:
        return sum(1 for check in self.checks if check.status == "fail")

    @property
    def skip_count(self) -> int:
        return sum(1 for check in self.checks if check.status == "skip")

    @property
    def ok(self) -> bool:
        return self.fail_count == 0

    def add(self, status: CheckStatus, item: str, detail: str, hint: str = "") -> None:
        self.checks.append(PreflightCheckResult(status=status, item=item, detail=detail, hint=hint))

    def iter_status(self, *statuses: CheckStatus) -> Iterable[PreflightCheckResult]:
        active = set(statuses)
        for check in self.checks:
            if check.status in active:
                yield check

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": __version__,
            "mode": self.mode,
            "generated_at": self.generated_at,
            "config_path": self.config_path,
            "summary": {
                "pass": self.pass_count,
                "warn": self.warn_count,
                "fail": self.fail_count,
                "skip": self.skip_count,
                "ok": self.ok,
            },
            "checks": [
                {
                    "status": check.status,
                    "item": check.item,
                    "detail": check.detail,
                    "hint": check.hint,
                }
                for check in self.checks
            ],
        }


def run_preflight(
    config_path: str | None = None,
    *,
    mode: Literal["startup", "doctor"] = "startup",
) -> PreflightReport:
    """Run shared environment/config checks for startup and doctor."""

    layout = get_config_layout(config_path)
    report = PreflightReport(mode=mode, config_path=str(layout.config_path))
    report.add(*_python_version_check())

    if layout.config_path.exists():
        report.add("pass", "Config file", f"???: {layout.config_path}")
    else:
        report.add(
            "fail",
            "Config file",
            f"??: {layout.config_path}",
            hint="???? `config/config.yaml` ?????? `CONFIG_PATH` ?????????",
        )
        return report

    try:
        config = load_config(config_path)
    except Exception as exc:
        report.add(
            "fail",
            "Config load",
            f"????: {exc}",
            hint="???? `config/config.yaml` ????????????? `newspulse doctor`?",
        )
        return report

    report.config = config
    report.add("pass", "Config load", f"loaded: {layout.config_path}")

    ctx = AppContext(config)
    try:
        _check_schedule(report, ctx)
        _check_selection_inputs(report, ctx)
        _check_ai_runtime(report, ctx)
        _check_notification(report, ctx)
        _check_storage(report, ctx)
        _check_output_dir(report, config)
    finally:
        ctx.cleanup()

    timeline_path = resolve_timeline_path(config_root=layout.config_root)
    if timeline_path.exists():
        report.add("pass", "Timeline file", f"???: {timeline_path}")
    else:
        report.add(
            "warn",
            "Timeline file",
            f"???: {timeline_path}???????????",
            hint="??????????? `config/timeline.yaml`?",
        )
    return report


def _python_version_check() -> tuple[CheckStatus, str, str, str]:
    required = _load_required_python_version()
    current = sys.version_info[:3]
    current_text = ".".join(str(part) for part in current)
    required_text = ".".join(str(part) for part in required)
    if current >= required:
        return "pass", "Python version", f"{current_text} (?? >= {required_text})", ""
    return (
        "fail",
        "Python version",
        f"{current_text} (??? >= {required_text})",
        "???????? Python ?????????????? `pyproject.toml`?",
    )


def _load_required_python_version() -> tuple[int, int, int]:
    project_root = get_config_layout().project_root
    pyproject_path = project_root / "pyproject.toml"
    fallback = (3, 12, 0)
    if not pyproject_path.exists():
        return fallback
    try:
        data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    except Exception:
        return fallback
    raw_value = str(data.get("project", {}).get("requires-python", "") or "").strip()
    if not raw_value.startswith(">="):
        return fallback
    version_text = raw_value[2:].strip()
    pieces = [piece for piece in version_text.split(".") if piece.isdigit()]
    if not pieces:
        return fallback
    while len(pieces) < 3:
        pieces.append("0")
    try:
        return int(pieces[0]), int(pieces[1]), int(pieces[2])
    except (TypeError, ValueError):
        return fallback


def _check_schedule(report: PreflightReport, ctx: AppContext) -> None:
    try:
        schedule = ctx.create_scheduler().resolve()
        report.add(
            "pass",
            "Schedule",
            f"???? (report_mode={schedule.report_mode}, ai_mode={schedule.ai_mode})",
        )
    except Exception as exc:
        report.add(
            "fail",
            "Schedule",
            f"????: {exc}",
            hint="??? `config/timeline.yaml` ?? `schedule` ?????????? preset ?????",
        )


def _check_selection_inputs(report: PreflightReport, ctx: AppContext) -> None:
    strategy = ctx.filter_method
    selection_config = ctx.selection_stage_config
    selection_ai = selection_config.get("AI", {}) if isinstance(selection_config, dict) else {}
    frequency_required = strategy == "keyword" or (
        strategy == "ai" and bool(selection_ai.get("FALLBACK_TO_KEYWORD", True))
    )

    if frequency_required:
        filter_config = ctx.config.get("FILTER", {})
        frequency_file = filter_config.get("FREQUENCY_FILE") if isinstance(filter_config, dict) else None
        frequency_path = resolve_frequency_words_path(
            frequency_file,
            config_root=ctx.config_root,
        )
        if frequency_path.exists():
            report.add("pass", "Frequency words", f"???: {frequency_path}")
        else:
            report.add(
                "fail",
                "Frequency words",
                f"??: {frequency_path}",
                hint="???????????? `workflow.selection.frequency_file` / `FREQUENCY_WORDS_PATH`?",
            )
    else:
        report.add("skip", "Frequency words", "????? keyword ?????????")

    if strategy == "ai":
        interests_file = selection_ai.get("INTERESTS_FILE") if isinstance(selection_ai, dict) else None
        interests_path = resolve_ai_interests_path(interests_file, config_root=ctx.config_root)
        if interests_path.exists():
            report.add("pass", "AI interests", f"???: {interests_path}")
        else:
            report.add(
                "fail",
                "AI interests",
                f"??: {interests_path}",
                hint="??? interests ?????? `workflow.selection.ai.interests_file`?",
            )
    else:
        report.add("skip", "AI interests", "????? AI selection?????")


def _check_ai_runtime(report: PreflightReport, ctx: AppContext) -> None:
    strategy = ctx.filter_method
    insight_config = ctx.ai_analysis_config
    selection_config = ctx.selection_stage_config
    insight_enabled = bool(insight_config.get("ENABLED", False)) and str(insight_config.get("STRATEGY", "noop") or "noop") == "ai"
    selection_ai_enabled = strategy == "ai"
    semantic_config = selection_config.get("SEMANTIC", {}) if isinstance(selection_config, dict) else {}
    semantic_enabled = selection_ai_enabled and bool(semantic_config.get("ENABLED", True))

    if selection_ai_enabled:
        _check_runtime_mapping(
            report,
            item="AI selection runtime",
            config=ctx.ai_filter_model_config,
            hint="??? `.env` / `config/config.yaml` ? selection ??????API Key ? API Base?",
        )
        _check_prompt_files(
            report,
            item="AI selection prompts",
            paths=[
                ctx.ai_filter_config.get("PROMPT_FILE"),
                ctx.ai_filter_config.get("EXTRACT_PROMPT_FILE"),
                ctx.ai_filter_config.get("UPDATE_TAGS_PROMPT_FILE"),
            ],
            hint="??? `config/ai_filter/` ???? prompt ?????? selection prompt ???",
        )
    else:
        report.add("skip", "AI selection runtime", "????? AI selection?????")
        report.add("skip", "AI selection prompts", "????? AI selection?????")

    if semantic_enabled:
        embedding_config = EmbeddingRuntimeConfig.from_mapping(ctx.ai_filter_embedding_model_config)
        try:
            embedding_config.validate()
            report.add("pass", "Semantic embedding", f"embedding model: {embedding_config.model}")
        except AIConfigError as exc:
            report.add(
                "fail",
                "Semantic embedding",
                str(exc),
                hint="??? `.env` ? `EMB_MODEL`?????? provider ? embedding API key ???",
            )
    else:
        report.add("skip", "Semantic embedding", "????? semantic recall?????")

    if insight_enabled:
        _check_runtime_mapping(
            report,
            item="AI insight runtime",
            config=ctx.ai_analysis_model_config,
            hint="??? `.env` / `config/config.yaml` ? insight ??????API Key ? API Base?",
        )
        _check_prompt_files(
            report,
            item="AI insight prompts",
            paths=[
                ctx.ai_analysis_config.get("PROMPT_FILE"),
                ctx.ai_analysis_config.get("ITEM_PROMPT_FILE"),
            ],
            hint="??? `config/` ???? insight prompt ?????? insight prompt ???",
        )
    else:
        report.add("skip", "AI insight runtime", "????? AI insight?????")
        report.add("skip", "AI insight prompts", "????? AI insight?????")


def _check_runtime_mapping(report: PreflightReport, *, item: str, config: dict[str, Any], hint: str) -> None:
    valid, message = AIRuntimeClient(config).validate_config()
    if valid:
        report.add("pass", item, f"model: {config.get('MODEL', '')}")
        return
    report.add("fail", item, message, hint=hint)


def _check_prompt_files(
    report: PreflightReport,
    *,
    item: str,
    paths: list[Any],
    hint: str,
) -> None:
    missing = [str(Path(path)) for path in paths if path and not Path(path).exists()]
    if missing:
        report.add("fail", item, f"??: {', '.join(missing)}", hint=hint)
        return
    existing = [str(Path(path)) for path in paths if path]
    report.add("pass", item, f"???: {', '.join(existing)}")


def _check_notification(report: PreflightReport, ctx: AppContext) -> None:
    if not ctx.notification_enabled:
        report.add("skip", "Notification", "??????????????")
        return
    if ctx.generic_webhook_url:
        report.add("pass", "Notification", "??? Generic Webhook ??")
        return
    report.add(
        "warn",
        "Notification",
        "?????????",
        hint="????????? `config/config.yaml` ???????? `GENERIC_WEBHOOK_URL`?",
    )


def _check_storage(report: PreflightReport, ctx: AppContext) -> None:
    try:
        storage_manager = ctx.get_storage_manager()
        detail = f"????: {storage_manager.backend_name}"
        if ctx.storage_retention_days > 0:
            detail += f"?????: {ctx.storage_retention_days} ?"
        report.add("pass", "Storage", detail)
    except Exception as exc:
        report.add(
            "fail",
            "Storage",
            f"????: {exc}",
            hint="??? `storage` ??????????",
        )


def _check_output_dir(report: PreflightReport, config: dict[str, Any]) -> None:
    try:
        output_dir = _resolve_output_dir(config)
        output_dir.mkdir(parents=True, exist_ok=True)
        probe_file = output_dir / ".preflight_write_probe"
        probe_file.write_text("ok", encoding="utf-8")
        probe_file.unlink(missing_ok=True)
        report.add("pass", "Output dir", f"??: {output_dir}")
    except Exception as exc:
        report.add(
            "fail",
            "Output dir",
            f"???: {exc}",
            hint="??? `storage.local.data_dir` ????????????",
        )


def _resolve_output_dir(config: dict[str, Any]) -> Path:
    storage = config.get("STORAGE", {}) if isinstance(config, dict) else {}
    local = storage.get("LOCAL", {}) if isinstance(storage, dict) else {}
    return Path(local.get("DATA_DIR", "output") or "output")
