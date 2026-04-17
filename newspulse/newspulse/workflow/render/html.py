# coding=utf-8
"""HTML adapter for the workflow render stage."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from newspulse.report import render_html_content
from newspulse.workflow.render.models import HTMLArtifact, RenderViewModel


class HTMLRenderAdapter:
    """Render a native render view model into the HTML output structure."""

    def __init__(
        self,
        *,
        output_dir: str = "output",
        get_time_func: Callable[[], Any] | None = None,
        date_folder_func: Callable[[], str] | None = None,
        time_filename_func: Callable[[], str] | None = None,
        region_order: list[str] | None = None,
        display_mode: str = "keyword",
        show_new_section: bool = True,
    ):
        self.output_dir = output_dir
        self.get_time_func = get_time_func
        self.date_folder_func = date_folder_func
        self.time_filename_func = time_filename_func
        self.region_order = list(region_order or ["hotlist", "new_items", "standalone", "ai_analysis"])
        self.display_mode = display_mode
        self.show_new_section = show_new_section

    def run(
        self,
        view_model: RenderViewModel,
        *,
        update_info: dict[str, Any] | None = None,
        region_order: list[str] | None = None,
        show_new_section: bool | None = None,
    ) -> HTMLArtifact:
        """Render and persist the HTML report."""

        mode = view_model.mode
        effective_region_order = list(region_order or self.region_order)
        effective_show_new_section = self.show_new_section if show_new_section is None else show_new_section
        html_content = render_html_content(
            view_model,
            update_info=update_info,
            region_order=effective_region_order,
            get_time_func=self.get_time_func,
            show_new_section=effective_show_new_section,
        )

        date_folder = self.date_folder_func() if self.date_folder_func else ""
        time_filename = self.time_filename_func() if self.time_filename_func else "latest"
        snapshot_dir = Path(self.output_dir) / "html" / date_folder
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = snapshot_dir / f"{time_filename}.html"
        snapshot_path.write_text(html_content, encoding="utf-8")

        latest_dir = Path(self.output_dir) / "html" / "latest"
        latest_dir.mkdir(parents=True, exist_ok=True)
        latest_path = latest_dir / f"{mode}.html"
        latest_path.write_text(html_content, encoding="utf-8")

        index_path = Path(self.output_dir) / "index.html"
        index_path.write_text(html_content, encoding="utf-8")

        return HTMLArtifact(
            file_path=str(snapshot_path),
            content=html_content,
        )
