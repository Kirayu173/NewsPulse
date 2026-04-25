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
from newspulse.core.config_paths import (
    get_config_layout,
    resolve_ai_interests_path,
    resolve_frequency_words_path,
    resolve_timeline_path,
)
from newspulse.core.loader import load_config
from newspulse.runtime import ApplicationRuntime, build_runtime
from newspulse.workflow.shared.ai_runtime.client import AIRuntimeClient
from newspulse.workflow.shared.ai_runtime.embedding import EmbeddingRuntimeClient, EmbeddingRuntimeConfig
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
        report.add("pass", "Config file", f"found: {layout.config_path}")
    else:
        report.add(
            "fail",
            "Config file",
            f"missing: {layout.config_path}",
            hint="Create `config/config.yaml` or point `CONFIG_PATH` to a valid config file.",
        )
        return report

    try:
        config = load_config(config_path)
    except Exception as exc:
        report.add(
            "fail",
            "Config load",
            f"load failed: {exc}",
            hint="Check whether `config/config.yaml` is valid YAML, then rerun `newspulse doctor`.",
        )
        return report

    report.config = config
    report.add("pass", "Config load", f"loaded: {layout.config_path}")

    runtime = build_runtime(config)
    try:
        _check_schedule(report, runtime)
        _check_selection_inputs(report, runtime)
        _check_ai_runtime(report, runtime)
        _check_notification(report, runtime)
        _check_storage(report, runtime)
        _check_output_dir(report, runtime.settings.storage.data_dir)
    finally:
        runtime.cleanup()

    timeline_path = resolve_timeline_path(config_root=layout.config_root)
    if timeline_path.exists():
        report.add("pass", "Timeline file", f"found: {timeline_path}")
    else:
        report.add(
            "warn",
            "Timeline file",
            f"missing: {timeline_path}; scheduler will fall back to defaults",
            hint="Add `config/timeline.yaml` if you need custom scheduling.",
        )
    return report


def _python_version_check() -> tuple[CheckStatus, str, str, str]:
    required = _load_required_python_version()
    current = sys.version_info[:3]
    current_text = ".".join(str(part) for part in current)
    required_text = ".".join(str(part) for part in required)
    if current >= required:
        return "pass", "Python version", f"{current_text} (meets >= {required_text})", ""
    return (
        "fail",
        "Python version",
        f"{current_text} (needs >= {required_text})",
        "Use the Python version declared in `pyproject.toml`.",
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


def _check_schedule(report: PreflightReport, runtime: ApplicationRuntime) -> None:
    try:
        schedule = runtime.container.scheduler().resolve()
        report.add(
            "pass",
            "Schedule",
            f"resolved (report_mode={schedule.report_mode}, ai_mode={schedule.ai_mode})",
        )
    except Exception as exc:
        report.add(
            "fail",
            "Schedule",
            f"resolve failed: {exc}",
            hint="Check `config/timeline.yaml` and the `schedule` preset name in config.",
        )


def _check_selection_inputs(report: PreflightReport, runtime: ApplicationRuntime) -> None:
    settings = runtime.settings
    strategy = settings.selection.strategy
    frequency_required = strategy == "keyword" or (
        strategy == "ai" and settings.selection.ai.fallback_to_keyword
    )

    if frequency_required:
        frequency_path = resolve_frequency_words_path(
            settings.selection.frequency_file,
            config_root=settings.paths.config_root,
        )
        if frequency_path.exists():
            report.add("pass", "Frequency words", f"found: {frequency_path}")
        else:
            report.add(
                "fail",
                "Frequency words",
                f"missing: {frequency_path}",
                hint="Set `workflow.selection.frequency_file` or `FREQUENCY_WORDS_PATH` to a valid file.",
            )
    else:
        report.add("skip", "Frequency words", "not required because keyword fallback is disabled")

    if strategy == "ai":
        interests_path = resolve_ai_interests_path(
            settings.selection.ai.interests_file,
            config_root=settings.paths.config_root,
        )
        if interests_path.exists():
            report.add("pass", "AI interests", f"found: {interests_path}")
        else:
            report.add(
                "fail",
                "AI interests",
                f"missing: {interests_path}",
                hint="Set `workflow.selection.ai.interests_file` to a valid interests file.",
            )
    else:
        report.add("skip", "AI interests", "not required because AI selection is disabled")


def _check_ai_runtime(report: PreflightReport, runtime: ApplicationRuntime) -> None:
    settings = runtime.settings
    selection_ai_enabled = settings.selection.strategy == "ai"
    semantic_enabled = selection_ai_enabled and settings.selection.semantic.enabled
    insight_enabled = settings.insight.enabled and settings.insight.strategy == "ai"

    if selection_ai_enabled:
        _check_runtime_mapping(
            report,
            item="AI selection runtime",
            config=settings.selection.ai_runtime_config,
            hint="Check the selection runtime fields in `.env` or `config/config.yaml`, especially model, API key, and base URL.",
        )
        _check_prompt_files(
            report,
            item="AI selection prompts",
            paths=[
                settings.selection.filter_config.get("PROMPT_FILE"),
                settings.selection.filter_config.get("EXTRACT_PROMPT_FILE"),
                settings.selection.filter_config.get("UPDATE_TAGS_PROMPT_FILE"),
            ],
            hint="Make sure the selection prompt files under `config/ai_filter/` exist and are readable.",
        )
    else:
        report.add("skip", "AI selection runtime", "not required because AI selection is disabled")
        report.add("skip", "AI selection prompts", "not required because AI selection is disabled")

    if semantic_enabled:
        _check_embedding_runtime(
            report,
            item="Semantic embedding",
            config=settings.selection.embedding_runtime_config,
            hint="Set `AI_EMBEDDING_MODEL` / `AI_EMBEDDING_API_KEY` / `AI_EMBEDDING_BASE_URL` in `.env`.",
        )
    else:
        report.add("skip", "Semantic embedding", "not required because semantic recall is disabled")

    if insight_enabled:
        _check_runtime_mapping(
            report,
            item="AI global insight runtime",
            config=settings.insight.ai_runtime_config,
            hint="Check the insight runtime fields in `.env` or `config/config.yaml`, especially model, API key, and base URL.",
        )
        _check_prompt_files(
            report,
            item="AI global insight prompt",
            paths=[
                settings.insight.analysis_config.get("PROMPT_FILE"),
            ],
            hint="Make sure the global insight prompt file under `config/` exists and is readable.",
        )
    else:
        report.add("skip", "AI global insight runtime", "not required because global insight is disabled")
        report.add("skip", "AI global insight prompt", "not required because global insight is disabled")


def _check_runtime_mapping(report: PreflightReport, *, item: str, config: dict[str, Any], hint: str) -> None:
    client = AIRuntimeClient(config)
    try:
        client.config.validate()
    except AIConfigError as exc:
        report.add("fail", item, str(exc), hint=hint)
    else:
        report.add("pass", item, client.runtime_summary())


def _check_embedding_runtime(report: PreflightReport, *, item: str, config: dict[str, Any], hint: str) -> None:
    embedding_config = EmbeddingRuntimeConfig.from_mapping(config)
    runtime = embedding_config.resolve_runtime()
    if not runtime.enabled:
        report.add(
            "warn",
            item,
            "embedding runtime not configured; semantic recall will auto-skip",
            hint=hint,
        )
        return
    try:
        embedding_config.validate()
    except AIConfigError as exc:
        report.add("fail", item, str(exc), hint=hint)
        return

    report.add("pass", item, EmbeddingRuntimeClient(config).runtime_summary())


def _check_prompt_files(
    report: PreflightReport,
    *,
    item: str,
    paths: list[Any],
    hint: str,
) -> None:
    missing = [str(Path(path)) for path in paths if path and not Path(path).exists()]
    if missing:
        report.add("fail", item, f"missing: {', '.join(missing)}", hint=hint)
        return
    existing = [str(Path(path)) for path in paths if path]
    report.add("pass", item, f"found: {', '.join(existing)}")


def _check_notification(report: PreflightReport, runtime: ApplicationRuntime) -> None:
    settings = runtime.settings
    if not settings.delivery.enabled:
        report.add("skip", "Notification", "not required because notifications are disabled")
        return
    if settings.delivery.generic_webhook_url:
        report.add("pass", "Notification", "configured: Generic Webhook")
        return
    report.add(
        "warn",
        "Notification",
        "enabled but no delivery channel is configured",
        hint="Configure a channel in `config/config.yaml` or set `GENERIC_WEBHOOK_URL`.",
    )


def _check_storage(report: PreflightReport, runtime: ApplicationRuntime) -> None:
    settings = runtime.settings
    try:
        storage_manager = runtime.container.storage()
        detail = f"backend: {storage_manager.backend_name}"
        if settings.storage.retention_days > 0:
            detail += f", retention_days: {settings.storage.retention_days}"
        report.add("pass", "Storage", detail)
    except Exception as exc:
        report.add(
            "fail",
            "Storage",
            f"init failed: {exc}",
            hint="Check the `storage` section in config.",
        )


def _check_output_dir(report: PreflightReport, output_dir: Path) -> None:
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        probe_file = output_dir / ".preflight_write_probe"
        probe_file.write_text("ok", encoding="utf-8")
        probe_file.unlink(missing_ok=True)
        report.add("pass", "Output dir", f"writable: {output_dir}")
    except Exception as exc:
        report.add(
            "fail",
            "Output dir",
            f"write failed: {exc}",
            hint="Check whether `storage.local.data_dir` points to a writable directory.",
        )
