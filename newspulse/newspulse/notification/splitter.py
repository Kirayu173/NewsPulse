# coding=utf-8
"""Split native render notifications into size-limited batches."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Callable, Dict, List, Optional

from newspulse.notification.batch import truncate_at_line_boundary
from newspulse.report.formatter import format_title_for_platform
from newspulse.utils.time import DEFAULT_TIMEZONE
from newspulse.workflow.render.insight import render_insight_markdown

if TYPE_CHECKING:
    from newspulse.workflow.render.models import RenderGroupView, RenderViewModel


DEFAULT_BATCH_SIZES = {
    "dingtalk": 20000,
    "feishu": 29000,
    "ntfy": 3800,
    "default": 4000,
}

DEFAULT_REGION_ORDER = ["hotlist", "new_items", "standalone", "insight"]
_SUPPORTED_FORMATS = {"wework", "bark", "telegram", "ntfy", "feishu", "dingtalk", "slack"}


def _channel_key(format_type: str) -> str:
    return format_type if format_type in _SUPPORTED_FORMATS else "wework"


def _bold(text: str, format_type: str) -> str:
    if format_type == "telegram":
        return text
    if format_type == "slack":
        return f"*{text}*"
    return f"**{text}**"


def _section_separator(format_type: str, feishu_separator: str) -> str:
    if format_type == "feishu":
        return f"\n{feishu_separator}\n\n"
    if format_type == "dingtalk":
        return "\n---\n\n"
    if format_type in ("wework", "bark"):
        return "\n\n\n\n"
    return "\n\n"


def _build_header(view_model: "RenderViewModel", format_type: str, now: datetime) -> str:
    lines = [f"{_bold('匹配标题', format_type)} {view_model.total_titles}"]

    ai_stats = view_model.insight.stats
    if ai_stats and ai_stats.get("analyzed_news", 0) > 0:
        analyzed_news = ai_stats.get("analyzed_news", 0)
        total_news = ai_stats.get("total_news", 0)
        ai_mode = ai_stats.get("ai_mode", "")
        display_value = str(analyzed_news)
        if total_news and total_news > analyzed_news:
            display_value = f"{analyzed_news}/{total_news}"

        mode_suffix = ""
        if ai_mode and ai_mode != view_model.mode:
            mode_map = {
                "daily": "日报",
                "current": "实时",
                "incremental": "增量",
            }
            mode_suffix = f" ({mode_map.get(ai_mode, ai_mode)})"
        lines.append(f"{_bold('AI 分析', format_type)} {display_value}{mode_suffix}")

    lines.extend(
        [
            f"{_bold('时间', format_type)} {now.strftime('%Y-%m-%d %H:%M:%S')}",
            f"{_bold('类型', format_type)} {view_model.report_type}",
            "",
        ]
    )

    if format_type in ("feishu", "dingtalk"):
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def _build_footer(format_type: str, now: datetime, update_info: Optional[Dict]) -> str:
    footer_lines: List[str] = []
    if format_type in ("wework", "bark", "ntfy", "dingtalk"):
        footer_lines.append(f"> 更新时间：{now.strftime('%Y-%m-%d %H:%M:%S')}")
        if update_info:
            footer_lines.append(
                f"> NewsPulse 可更新到 {update_info['remote_version']}（当前 {update_info['current_version']}）"
            )
    elif format_type == "telegram":
        footer_lines.append(f"更新时间：{now.strftime('%Y-%m-%d %H:%M:%S')}")
        if update_info:
            footer_lines.append(
                f"NewsPulse 可更新到 {update_info['remote_version']}（当前 {update_info['current_version']}）"
            )
    elif format_type == "slack":
        footer_lines.append(f"_更新时间：{now.strftime('%Y-%m-%d %H:%M:%S')}_")
        if update_info:
            footer_lines.append(
                f"_NewsPulse 可更新到 {update_info['remote_version']}（当前 {update_info['current_version']}）_"
            )
    elif format_type == "feishu":
        footer_lines.append(f"<font color='grey'>更新时间：{now.strftime('%Y-%m-%d %H:%M:%S')}</font>")
        if update_info:
            footer_lines.append(
                f"<font color='grey'>NewsPulse 可更新到 {update_info['remote_version']}（当前 {update_info['current_version']}）</font>"
            )

    if not footer_lines:
        return ""
    return "\n\n" + "\n".join(footer_lines)


def _build_hotlist_section(groups: list["RenderGroupView"], format_type: str, display_mode: str) -> str:
    if not groups:
        return ""

    total_items = sum(len(group.items) for group in groups if group.count > 0)
    if total_items <= 0:
        return ""

    section_title = "热榜关键词" if display_mode == "keyword" else "热榜平台"
    lines = [f"{_bold(section_title, format_type)} (共 {total_items} 条)", ""]
    channel = _channel_key(format_type)
    total_groups = len(groups)

    for index, group in enumerate(groups, start=1):
        if not group.items:
            continue
        lines.append(f"[{index}/{total_groups}] {_bold(group.label, format_type)} · {group.count or len(group.items)}条")
        for title_index, item in enumerate(group.items, start=1):
            formatted = format_title_for_platform(
                channel,
                item.to_formatter_payload(),
                show_source=display_mode == "keyword",
                show_keyword=display_mode != "keyword",
            )
            lines.append(f"  {title_index}. {formatted}")
        lines.append("")

    return "\n".join(lines).strip()


def _build_new_items_section(groups: list["RenderGroupView"], format_type: str, total_new_count: int) -> str:
    if not groups or total_new_count <= 0:
        return ""

    lines = [f"{_bold('本次新增热点', format_type)} (共 {total_new_count} 条)", ""]
    channel = _channel_key(format_type)
    for group in groups:
        if not group.items:
            continue
        lines.append(f"{_bold(group.label, format_type)} · {len(group.items)}条")
        for index, item in enumerate(group.items, start=1):
            formatted = format_title_for_platform(channel, item.to_formatter_payload(), show_source=False)
            lines.append(f"  {index}. {formatted}")
        lines.append("")

    return "\n".join(lines).strip()


def _build_standalone_section(groups: list["RenderGroupView"], format_type: str) -> str:
    if not groups:
        return ""

    total_items = sum(len(group.items) for group in groups)
    if total_items <= 0:
        return ""

    lines = [f"{_bold('独立展示区', format_type)} (共 {total_items} 条)", ""]
    channel = _channel_key(format_type)

    for group in groups:
        if not group.items:
            continue
        lines.append(f"{_bold(group.label, format_type)} · {len(group.items)}条")
        for index, item in enumerate(group.items, start=1):
            formatted = format_title_for_platform(channel, item.to_formatter_payload(), show_source=False)
            lines.append(f"  {index}. {formatted}")
        lines.append("")

    return "\n".join(lines).strip()


def _build_failed_section(failed_ids: list[str], format_type: str) -> str:
    if not failed_ids:
        return ""

    lines = [f"{_bold('抓取失败来源', format_type)}", ""]
    for failed_id in failed_ids:
        lines.append(f"- {failed_id}")
    return "\n".join(lines).strip()


def _build_empty_message(mode: str) -> str:
    if mode == "incremental":
        return "本次没有新增热榜内容"
    if mode == "current":
        return "当前没有匹配的热榜内容"
    return "今日暂无热榜内容"


def _split_content_by_lines(content: str, footer: str, max_bytes: int, base_header: str) -> List[str]:
    footer_size = len(footer.encode("utf-8"))
    batches: List[str] = []
    current = ""

    for line in content.splitlines(keepends=True):
        candidate = current + line
        if len((candidate + footer).encode("utf-8")) <= max_bytes:
            current = candidate
            continue

        if current.strip():
            batches.append(current + footer)
            current = base_header

        candidate = current + line
        if len((candidate + footer).encode("utf-8")) <= max_bytes:
            current = candidate
            continue

        available = max_bytes - footer_size - len(current.encode("utf-8"))
        chunk = truncate_at_line_boundary(line, max(available, 0))
        if chunk:
            current += chunk
            batches.append(current + footer)
            remainder = line[len(chunk):]
        else:
            remainder = line

        current = base_header
        while remainder:
            available = max_bytes - footer_size - len(base_header.encode("utf-8"))
            chunk = truncate_at_line_boundary(remainder, max(available, 0))
            if not chunk:
                break
            batches.append(base_header + chunk + footer)
            remainder = remainder[len(chunk):]

    if current.strip():
        batches.append(current + footer)

    return batches or [truncate_at_line_boundary(content + footer, max_bytes)]


def split_content_into_batches(
    view_model: "RenderViewModel",
    format_type: str,
    update_info: Optional[Dict] = None,
    max_bytes: Optional[int] = None,
    batch_sizes: Optional[Dict[str, int]] = None,
    feishu_separator: str = "---",
    region_order: Optional[List[str]] = None,
    get_time_func: Optional[Callable[[], datetime]] = None,
    timezone: str = DEFAULT_TIMEZONE,
    show_new_section: bool = True,
) -> List[str]:
    del timezone

    if region_order is None:
        region_order = DEFAULT_REGION_ORDER

    sizes = {**DEFAULT_BATCH_SIZES, **(batch_sizes or {})}
    if max_bytes is None:
        if format_type == "dingtalk":
            max_bytes = sizes.get("dingtalk", 20000)
        elif format_type == "feishu":
            max_bytes = sizes.get("feishu", 29000)
        elif format_type == "ntfy":
            max_bytes = sizes.get("ntfy", 3800)
        else:
            max_bytes = sizes.get("default", 4000)

    now = get_time_func() if get_time_func else datetime.now()
    header = _build_header(view_model, format_type, now)
    footer = _build_footer(format_type, now, update_info)

    sections = {
        "hotlist": _build_hotlist_section(view_model.hotlist_groups, format_type, view_model.display_mode),
        "new_items": (
            _build_new_items_section(view_model.new_item_groups, format_type, view_model.total_new_items)
            if show_new_section
            else ""
        ),
        "standalone": _build_standalone_section(view_model.standalone_groups, format_type),
        "insight": render_insight_markdown(view_model.insight).strip(),
        "failed": _build_failed_section(view_model.failed_source_names, format_type),
    }

    ordered_sections: List[str] = []
    for region in region_order:
        section = sections.get(region, "")
        if section:
            ordered_sections.append(section)
    if sections["failed"]:
        ordered_sections.append(sections["failed"])

    if not ordered_sections:
        body = header + _build_empty_message(view_model.mode) + "\n"
        return _split_content_by_lines(body, footer, max_bytes, header)

    body = header + _section_separator(format_type, feishu_separator).join(ordered_sections) + "\n"
    return _split_content_by_lines(body, footer, max_bytes, header)
