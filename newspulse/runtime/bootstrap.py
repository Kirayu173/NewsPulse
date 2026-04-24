# coding=utf-8
"""Runtime bootstrap helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from newspulse.runtime.container import RuntimeContainer, RuntimeProviders
from newspulse.runtime.delivery_context import DeliveryOptionsBuilder
from newspulse.runtime.insight_context import InsightOptionsBuilder
from newspulse.runtime.render_context import RenderOptionsBuilder
from newspulse.runtime.selection_context import SelectionOptionsBuilder
from newspulse.runtime.settings import RuntimeSettings


@dataclass(slots=True)
class ApplicationRuntime:
    """Explicit runtime bundle shared by entrypoints."""

    settings: RuntimeSettings
    container: RuntimeContainer
    selection_builder: SelectionOptionsBuilder
    insight_builder: InsightOptionsBuilder
    render_builder: RenderOptionsBuilder
    delivery_builder: DeliveryOptionsBuilder

    @classmethod
    def from_mapping(
        cls,
        config: Mapping[str, Any] | None,
        *,
        providers: RuntimeProviders | None = None,
    ) -> ApplicationRuntime:
        settings = RuntimeSettings.from_mapping(config)
        container = RuntimeContainer(settings, providers=providers)
        return cls(
            settings=settings,
            container=container,
            selection_builder=SelectionOptionsBuilder(settings),
            insight_builder=InsightOptionsBuilder(settings),
            render_builder=RenderOptionsBuilder(settings),
            delivery_builder=DeliveryOptionsBuilder(settings),
        )

    def cleanup(self) -> None:
        self.container.cleanup()


def build_runtime(
    config: Mapping[str, Any] | None,
    *,
    providers: RuntimeProviders | None = None,
) -> ApplicationRuntime:
    return ApplicationRuntime.from_mapping(config, providers=providers)
