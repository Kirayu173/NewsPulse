# coding=utf-8
"""Split hotlist notifications into size-limited batches."""

from __future__ import annotations

from datetime import datetime
from typing import Callable, Dict, List, Optional

from newspulse.notification.batch import truncate_at_line_boundary
from newspulse.report.formatter import format_title_for_platform
from newspulse.utils.time import DEFAULT_TIMEZONE


DEFAULT_BATCH_SIZES = {
    "dingtalk": 20000,
    "feishu": 29000,
    "ntfy": 3800,
    "default": 4000,
}

DEFAULT_REGION_ORDER = ["hotlist", "new_items", "standalone", "ai_analysis"]
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


def _build_header(
    total_titles: int,
    format_type: str,
    report_type: str,
    now: datetime,
    ai_stats: Optional[Dict],
    mode: str,
) -> str:
    lines = [f"{_bold('匹配标题', format_type)} {total_titles}"]

    if ai_stats and ai_stats.get("analyzed_news", 0) > 0:
        analyzed_news = ai_stats.get("analyzed_news", 0)
        total_news = ai_stats.get("total_news", 0)
        ai_mode = ai_stats.get("ai_mode", "")
        display_value = str(analyzed_news)
        if total_news and total_news > analyzed_news:
            display_value = f"{analyzed_news}/{total_news}"

        mode_suffix = ""
        if ai_mode and ai_mode != mode:
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
            f"{_bold('类型', format_type)} {report_type}",
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


def _build_hotlist_section(report_data: Dict, format_type: str, display_mode: str) -> str:
    stats = report_data.get("stats", [])
    if not stats:
        return ""

    total_items = sum(len(stat.get("titles", [])) for stat in stats if stat.get("count", 0) > 0)
    if total_items <= 0:
        return ""

    section_title = "热榜关键词" if display_mode == "keyword" else "热榜平台"
    lines = [f"{_bold(section_title, format_type)} (共 {total_items} 条)", ""]
    channel = _channel_key(format_type)
    total_groups = len(stats)

    for index, stat in enumerate(stats, start=1):
        titles = stat.get("titles", [])
        if not titles:
            continue
        word = stat.get("word", "未命名分组")
        lines.append(f"[{index}/{total_groups}] {_bold(word, format_type)} · {stat.get('count', len(titles))}条")
        for title_index, title_data in enumerate(titles, start=1):
            formatted = format_title_for_platform(
                channel,
                title_data,
                show_source=display_mode == "keyword",
                show_keyword=display_mode != "keyword",
            )
            lines.append(f"  {title_index}. {formatted}")
        lines.append("")

    return "\n".join(lines).strip()


def _build_new_items_section(report_data: Dict, format_type: str) -> str:
    new_titles = report_data.get("new_titles", [])
    total_new_count = report_data.get("total_new_count", 0)
    if not new_titles or total_new_count <= 0:
        return ""

    lines = [f"{_bold('本次新增热点', format_type)} (共 {total_new_count} 条)", ""]
    channel = _channel_key(format_type)
    for source in new_titles:
        source_name = source.get("source_name", source.get("source_id", "未知来源"))
        titles = source.get("titles", [])
        if not titles:
            continue
        lines.append(f"{_bold(source_name, format_type)} · {len(titles)}条")
        for index, title_data in enumerate(titles, start=1):
            formatted = format_title_for_platform(channel, title_data, show_source=False)
            lines.append(f"  {index}. {formatted}")
        lines.append("")

    return "\n".join(lines).strip()


def _build_standalone_section(
    standalone_data: Optional[Dict],
    format_type: str,
    rank_threshold: int,
) -> str:
    if not standalone_data:
        return ""

    platforms = standalone_data.get("platforms", [])
    total_items = sum(len(platform.get("items", [])) for platform in platforms)
    if total_items <= 0:
        return ""

    lines = [f"{_bold('独立展示区', format_type)} (共 {total_items} 条)", ""]
    channel = _channel_key(format_type)

    for platform in platforms:
        platform_name = platform.get("name", platform.get("id", "未知平台"))
        items = platform.get("items", [])
        if not items:
            continue
        lines.append(f"{_bold(platform_name, format_type)} · {len(items)}条")
        for index, item in enumerate(items, start=1):
            title_data = {
                "title": item.get("title", ""),
                "source_name": platform_name,
                "time_display": item.get("time_display", ""),
                "count": item.get("count", 1),
                "ranks": item.get("ranks", []),
                "rank_threshold": rank_threshold,
                "url": item.get("url", ""),
                "mobile_url": item.get("mobileUrl", item.get("mobile_url", "")),
                "is_new": False,
            }
            formatted = format_title_for_platform(channel, title_data, show_source=False)
            lines.append(f"  {index}. {formatted}")
        lines.append("")

    return "\n".join(lines).strip()


def _build_failed_section(report_data: Dict, format_type: str) -> str:
    failed_ids = report_data.get("failed_ids", [])
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
    report_data: Dict,
    format_type: str,
    update_info: Optional[Dict] = None,
    max_bytes: Optional[int] = None,
    mode: str = "daily",
    batch_sizes: Optional[Dict[str, int]] = None,
    feishu_separator: str = "---",
    region_order: Optional[List[str]] = None,
    get_time_func: Optional[Callable[[], datetime]] = None,
    timezone: str = DEFAULT_TIMEZONE,
    display_mode: str = "keyword",
    ai_content: Optional[str] = None,
    standalone_data: Optional[Dict] = None,
    rank_threshold: int = 10,
    ai_stats: Optional[Dict] = None,
    report_type: str = "热榜通知",
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
    total_titles = sum(
        len(stat.get("titles", []))
        for stat in report_data.get("stats", [])
        if stat.get("count", 0) > 0
    )

    header = _build_header(total_titles, format_type, report_type, now, ai_stats, mode)
    footer = _build_footer(format_type, now, update_info)

    sections = {
        "hotlist": _build_hotlist_section(report_data, format_type, display_mode),
        "new_items": _build_new_items_section(report_data, format_type) if show_new_section else "",
        "standalone": _build_standalone_section(standalone_data, format_type, rank_threshold),
        "ai_analysis": ai_content.strip() if ai_content else "",
        "failed": _build_failed_section(report_data, format_type),
    }

    ordered_sections: List[str] = []
    for region in region_order:
        section = sections.get(region, "")
        if section:
            ordered_sections.append(section)
    if sections["failed"]:
        ordered_sections.append(sections["failed"])

    if not ordered_sections:
        body = header + _build_empty_message(mode) + "\n"
        return _split_content_by_lines(body, footer, max_bytes, header)

    body = header + _section_separator(format_type, feishu_separator).join(ordered_sections) + "\n"
    return _split_content_by_lines(body, footer, max_bytes, header)
