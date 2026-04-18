# coding=utf-8
"""Snapshot stage service."""

from __future__ import annotations

from typing import Any, Mapping

from newspulse.workflow.shared.contracts import HotlistSnapshot
from newspulse.workflow.shared.options import SnapshotOptions
from newspulse.workflow.snapshot.loader import SnapshotBundleLoader
from newspulse.workflow.snapshot.projector import SnapshotProjector


class SnapshotService:
    """Build the unique downstream snapshot from persisted hotlist data."""

    def __init__(
        self,
        storage_manager: Any,
        *,
        platform_ids: list[str] | None = None,
        platform_names: Mapping[str, str] | None = None,
        standalone_platform_ids: list[str] | None = None,
        standalone_max_items: int = 20,
    ):
        self.storage_manager = storage_manager
        self.platform_ids = list(platform_ids or [])
        self.platform_names = dict(platform_names or {})
        self.standalone_platform_ids = list(standalone_platform_ids or [])
        self.standalone_max_items = standalone_max_items
        self.loader = SnapshotBundleLoader(
            storage_manager,
            platform_ids=self.platform_ids,
            platform_names=self.platform_names,
        )
        self.projector = SnapshotProjector(
            standalone_platform_ids=self.standalone_platform_ids,
            standalone_max_items=self.standalone_max_items,
        )

    def build(self, options: SnapshotOptions) -> HotlistSnapshot:
        """Build a normalized workflow snapshot for the requested report mode."""

        bundle = self.loader.load(options.mode)
        projection = self.projector.build(bundle)
        return HotlistSnapshot(
            mode=options.mode,
            generated_at=bundle.latest_crawl_time,
            items=projection.items,
            failed_sources=projection.failed_sources,
            new_items=projection.new_items,
            standalone_sections=projection.standalone_sections,
            summary=projection.summary,
        )
