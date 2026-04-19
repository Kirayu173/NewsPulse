# coding=utf-8
"""AI-based insight strategy."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable

from newspulse.workflow.insight.models import (
    DEFAULT_SECTION_TEMPLATES,
    InsightPromptPayload,
    InsightSectionTemplate,
    build_summary,
)
from newspulse.workflow.shared.ai_runtime.client import AIRuntimeClient
from newspulse.workflow.shared.ai_runtime.codec import decode_json_response, extract_json_block
from newspulse.workflow.shared.ai_runtime.errors import AIResponseDecodeError
from newspulse.workflow.shared.ai_runtime.prompts import PromptTemplate, load_prompt_template
from newspulse.workflow.shared.contracts import InsightResult, InsightSection
from newspulse.workflow.shared.options import InsightOptions


class AIInsightStrategy:
    """Generate structured insight sections from snapshot and selection data."""

    REPORT_TYPE_BY_MODE = {
        "daily": "每日报告",
        "current": "实时报告",
        "incremental": "增量报告",
        "follow_report": "热点分析报告",
    }

    def __init__(
        self,
        *,
        ai_runtime_config: Mapping[str, Any] | None = None,
        analysis_config: Mapping[str, Any] | None = None,
        config_root: str | Path | None = None,
        client: AIRuntimeClient | Any | None = None,
        completion_func: Callable[..., Any] | None = None,
        prompt_template: PromptTemplate | None = None,
        section_templates: tuple[InsightSectionTemplate, ...] = DEFAULT_SECTION_TEMPLATES,
    ):
        self.analysis_config = dict(analysis_config or {})
        self.config_root = Path(config_root) if config_root is not None else None
        self.language = str(self.analysis_config.get("LANGUAGE", "Chinese"))
        self.section_templates = section_templates
        if client is None:
            if ai_runtime_config is None:
                raise ValueError("AI runtime config is required when no client is provided")
            client = AIRuntimeClient(ai_runtime_config, completion_func=completion_func)
        self.client = client
        self.prompt_template = prompt_template or load_prompt_template(
            self.analysis_config.get("PROMPT_FILE", "ai_analysis_prompt.txt"),
            config_root=self.config_root,
            required=True,
        )

    def run(self, snapshot: Any, selection: Any, options: InsightOptions) -> InsightResult:
        """Run AI insight generation for the selected hotlist items."""

        payload = self._build_prompt_payload(snapshot, selection, options)
        if not payload.news_content:
            return InsightResult(
                enabled=True,
                strategy="ai",
                diagnostics={
                    "mode": snapshot.mode,
                    "report_mode": options.mode,
                    "selected_items": selection.total_selected,
                    "analyzed_items": 0,
                    "max_items": options.max_items,
                    "skipped": True,
                    "reason": "no selected items available for insight generation",
                },
            )

        user_prompt = self._render_prompt(payload)
        raw_response = ""
        try:
            raw_response = self.client.chat(self.prompt_template.build_messages(user_prompt))
            parsed, parse_error = self._decode_response_payload(raw_response)
            sections = self._build_sections(parsed)
            diagnostics = {
                "mode": snapshot.mode,
                "report_mode": options.mode,
                "selected_items": selection.total_selected,
                "analyzed_items": payload.news_count,
                "max_items": options.max_items,
                "platform_count": len(payload.platforms),
                "keyword_count": len(payload.keywords),
                "standalone_included": bool(payload.standalone_content),
                "section_count": len(sections),
            }
            if parse_error:
                diagnostics["parse_error"] = parse_error
            return InsightResult(
                enabled=True,
                strategy="ai",
                sections=sections,
                raw_response=raw_response,
                diagnostics=diagnostics,
            )
        except Exception as exc:
            return InsightResult(
                enabled=True,
                strategy="ai",
                raw_response=raw_response,
                diagnostics={
                    "mode": snapshot.mode,
                    "report_mode": options.mode,
                    "selected_items": selection.total_selected,
                    "analyzed_items": payload.news_count,
                    "max_items": options.max_items,
                    "error": f"{type(exc).__name__}: {exc}",
                },
            )

    def _build_prompt_payload(self, snapshot: Any, selection: Any, options: InsightOptions) -> InsightPromptPayload:
        selected_items = list(getattr(selection, "qualified_items", None) or selection.selected_items or [])
        if options.max_items > 0:
            selected_items = selected_items[: options.max_items]

        platforms = []
        seen_platforms: set[str] = set()
        for item in selected_items:
            platform_name = item.source_name or item.source_id
            if platform_name and platform_name not in seen_platforms:
                seen_platforms.add(platform_name)
                platforms.append(platform_name)

        keywords = [
            str(label).strip()
            for label in selection.diagnostics.get("focus_labels", [])
            if str(label).strip()
        ]
        news_content = self._render_news_content(selected_items, include_rank_timeline=options.include_rank_timeline)
        standalone_content = ""
        if options.include_standalone:
            standalone_content = self._render_standalone_content(
                snapshot.standalone_sections,
                include_rank_timeline=options.include_rank_timeline,
            )

        current_time = snapshot.generated_at or ""
        report_mode = options.mode or snapshot.mode
        report_type = self.REPORT_TYPE_BY_MODE.get(report_mode, "热点分析报告")

        return InsightPromptPayload(
            report_mode=report_mode,
            report_type=report_type,
            current_time=current_time,
            news_count=len(selected_items),
            platforms=platforms,
            keywords=keywords,
            news_content=news_content,
            standalone_content=standalone_content,
            language=self.language,
        )

    def _render_prompt(self, payload: InsightPromptPayload) -> str:
        user_prompt = self.prompt_template.user_prompt
        replacements = {
            "report_mode": payload.report_mode,
            "report_type": payload.report_type,
            "current_time": payload.current_time,
            "news_count": str(payload.news_count),
            "platforms": ", ".join(payload.platforms) or "未指定",
            "keywords": ", ".join(payload.keywords) or "-",
            "news_content": payload.news_content,
            "standalone_content": payload.standalone_content,
            "language": payload.language,
        }
        for key, value in replacements.items():
            user_prompt = user_prompt.replace("{" + key + "}", value)
        return user_prompt

    @staticmethod
    def _render_news_content(selected_items: list[Any], *, include_rank_timeline: bool) -> str:
        lines: list[str] = []
        for item in selected_items:
            meta_parts = []
            if item.ranks:
                meta_parts.append(f"排名:{AIInsightStrategy._format_rank_range(item.ranks)}")
            time_range = AIInsightStrategy._format_time_range(item.first_time, item.last_time)
            if time_range:
                meta_parts.append(f"时间:{time_range}")
            if item.count > 1:
                meta_parts.append(f"次数:{item.count}次")
            if include_rank_timeline and item.rank_timeline:
                meta_parts.append(f"轨迹:{AIInsightStrategy._format_rank_timeline(item.rank_timeline)}")

            line = f"- [{item.source_name or item.source_id}] {item.title}"
            if meta_parts:
                line += " | " + " | ".join(meta_parts)
            lines.append(line)
        return "\n".join(lines).strip()

    @staticmethod
    def _render_standalone_content(sections: list[Any], *, include_rank_timeline: bool) -> str:
        lines: list[str] = []
        for section in sections or []:
            if not section.items:
                continue
            lines.append(f"### [{section.label}]")
            for item in section.items:
                meta_parts = []
                if item.ranks:
                    meta_parts.append(f"排名:{AIInsightStrategy._format_rank_range(item.ranks)}")
                time_range = AIInsightStrategy._format_time_range(item.first_time, item.last_time)
                if time_range:
                    meta_parts.append(f"时间:{time_range}")
                if item.count > 1:
                    meta_parts.append(f"次数:{item.count}次")
                if include_rank_timeline and item.rank_timeline:
                    meta_parts.append(f"轨迹:{AIInsightStrategy._format_rank_timeline(item.rank_timeline)}")

                line = f"- {item.title}"
                if meta_parts:
                    line += " | " + " | ".join(meta_parts)
                lines.append(line)
            lines.append("")
        return "\n".join(lines).strip()

    def _build_sections(self, payload: Any) -> list[InsightSection]:
        if not isinstance(payload, Mapping):
            return []

        sections: list[InsightSection] = []
        for template in self.section_templates:
            content = str(payload.get(template.field_name, "")).strip()
            if not content:
                continue
            sections.append(
                InsightSection(
                    key=template.key,
                    title=template.title,
                    content=content,
                    summary=build_summary(content, template.summary_limit),
                )
            )

        standalone = payload.get("standalone_summaries", {})
        if isinstance(standalone, Mapping):
            for platform_name, content in standalone.items():
                normalized_content = str(content).strip()
                normalized_name = str(platform_name).strip()
                if not normalized_name or not normalized_content:
                    continue
                sections.append(
                    InsightSection(
                        key=f"standalone:{normalized_name}",
                        title=f"Standalone / {normalized_name}",
                        content=normalized_content,
                        summary=build_summary(normalized_content),
                        metadata={"platform": normalized_name, "kind": "standalone_summary"},
                    )
                )
        return sections

    @staticmethod
    def _decode_response_payload(raw_response: str) -> tuple[Any, str]:
        """Decode the model payload and fall back to plain-text insight when JSON is invalid."""

        try:
            return decode_json_response(raw_response), ""
        except AIResponseDecodeError as exc:
            normalized = extract_json_block(raw_response) or (raw_response or "").strip()
            fallback_content = normalized[:500] + ("..." if len(normalized) > 500 else "")
            return {"core_trends": fallback_content}, str(exc)

    @staticmethod
    def _format_rank_range(ranks: list[int]) -> str:
        normalized = sorted(rank for rank in ranks if isinstance(rank, int) and rank > 0)
        if not normalized:
            return ""
        if normalized[0] == normalized[-1]:
            return str(normalized[0])
        return f"{normalized[0]}-{normalized[-1]}"

    @staticmethod
    def _format_time_range(first_time: str, last_time: str) -> str:
        def normalize(value: str) -> str:
            if not value:
                return ""
            value = str(value)
            if " " in value:
                value = value.split(" ", 1)[1]
            value = value.replace("-", ":")
            return value[:5] if ":" in value and len(value) >= 5 else value

        first = normalize(first_time)
        last = normalize(last_time)
        if first and last and first != last:
            return f"{first}~{last}"
        return first or last

    @staticmethod
    def _format_rank_timeline(rank_timeline: list[dict[str, Any]]) -> str:
        parts: list[str] = []
        for point in rank_timeline or []:
            time_value = str(point.get("time", "")).replace("-", ":")
            rank_value = point.get("rank")
            if not time_value:
                continue
            rank_text = "off" if rank_value in (None, 0) else str(rank_value)
            parts.append(f"{rank_text}({time_value})")
        return " -> ".join(parts)
