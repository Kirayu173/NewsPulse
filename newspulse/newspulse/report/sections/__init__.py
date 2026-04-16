# coding=utf-8
"""Section render helpers for HTML reports."""

from newspulse.report.sections.common import add_section_divider
from newspulse.report.sections.hotlist import render_hotlist_stats_html, render_new_titles_html
from newspulse.report.sections.standalone import render_standalone_html

__all__ = [
    "add_section_divider",
    "render_hotlist_stats_html",
    "render_new_titles_html",
    "render_standalone_html",
]
