# coding=utf-8
"""Runner environment and execution plan helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Mapping, Optional

from newspulse.core.scheduler import ResolvedSchedule


@dataclass(frozen=True)
class ModeStrategy:
    mode: str
    mode_name: str
    description: str
    report_type: str
    should_send_notification: bool = True


MODE_STRATEGIES: dict[str, ModeStrategy] = {
    "incremental": ModeStrategy(
        mode="incremental",
        mode_name="增量",
        description="仅分析本次抓取新增的热榜变化",
        report_type="增量报告",
    ),
    "current": ModeStrategy(
        mode="current",
        mode_name="实时",
        description="基于今日已抓取数据生成当前快照",
        report_type="实时报告",
    ),
    "daily": ModeStrategy(
        mode="daily",
        mode_name="日报",
        description="汇总今日全部抓取数据生成日报",
        report_type="每日报告",
    ),
}


@dataclass(frozen=True)
class RunnerEnvironment:
    is_github_actions: bool
    is_docker_container: bool

    @property
    def should_open_browser(self) -> bool:
        return not self.is_github_actions and not self.is_docker_container


@dataclass(frozen=True)
class WorkflowExecutionPlan:
    schedule: ResolvedSchedule
    report_mode: str
    mode_strategy: ModeStrategy
    frequency_file: Optional[str]
    filter_method: Optional[str]
    interests_file: Optional[str]


def resolve_mode_strategy(mode: str) -> ModeStrategy:
    return MODE_STRATEGIES.get(mode, MODE_STRATEGIES["daily"])


def detect_runner_environment(
    environ: Mapping[str, str] | None = None,
    *,
    path_exists: Callable[[str], bool] = os.path.exists,
) -> RunnerEnvironment:
    env = environ or os.environ
    is_github_actions = str(env.get("GITHUB_ACTIONS", "")).lower() == "true"
    is_docker_container = (
        str(env.get("DOCKER_CONTAINER", "")).lower() == "true"
        or path_exists("/.dockerenv")
    )
    return RunnerEnvironment(
        is_github_actions=is_github_actions,
        is_docker_container=is_docker_container,
    )
