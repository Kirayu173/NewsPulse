# coding=utf-8
"""AI analysis helpers for the hotlist-only runtime."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from newspulse.workflow.shared.ai_runtime.client import AIRuntimeClient
from newspulse.workflow.shared.ai_runtime.prompts import load_prompt_template


@dataclass
class AIAnalysisResult:
    """Structured AI analysis result."""

    core_trends: str = ""
    sentiment_controversy: str = ""
    signals: str = ""
    outlook_strategy: str = ""
    standalone_summaries: Dict[str, str] = field(default_factory=dict)

    raw_response: str = ""
    success: bool = False
    skipped: bool = False
    error: str = ""

    total_news: int = 0
    analyzed_news: int = 0
    max_news_limit: int = 0
    hotlist_count: int = 0
    ai_mode: str = ""


class AIAnalyzer:
    """Call the configured LLM to analyze hotlist data."""

    def __init__(
        self,
        ai_config: Dict[str, Any],
        analysis_config: Dict[str, Any],
        get_time_func: Callable,
        debug: bool = False,
    ):
        self.ai_config = ai_config
        self.analysis_config = analysis_config
        self.get_time_func = get_time_func
        self.debug = debug
        self.client = AIRuntimeClient(ai_config)

        valid, error = self.client.validate_config()
        if not valid:
            print(f"[AI] 配置异常: {error}")

        self.max_news = analysis_config.get("MAX_NEWS_FOR_ANALYSIS", 50)
        self.include_rank_timeline = analysis_config.get("INCLUDE_RANK_TIMELINE", False)
        self.include_standalone = analysis_config.get("INCLUDE_STANDALONE", False)
        self.language = analysis_config.get("LANGUAGE", "Chinese")
        prompt_template = load_prompt_template(
            analysis_config.get("PROMPT_FILE", "ai_analysis_prompt.txt"),
        )
        self.system_prompt = prompt_template.system_prompt
        self.user_prompt_template = prompt_template.user_prompt

    def analyze(
        self,
        stats: List[Dict],
        report_mode: str = "daily",
        report_type: str = "AI 分析",
        platforms: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        standalone_data: Optional[Dict] = None,
    ) -> AIAnalysisResult:
        """Analyze hotlist statistics with the configured model."""

        model = self.ai_config.get("MODEL", "unknown")
        api_key = self.client.config.api_key or ""
        api_base = self.ai_config.get("API_BASE", "")
        masked_key = f"{api_key[:5]}******" if len(api_key) >= 5 else "******"

        print(f"[AI] 模型: {model}")
        print(f"[AI] Key : {masked_key}")
        if api_base:
            print("[AI] Base: 使用自定义 API 地址")
        print(
            f"[AI] 参数: timeout={self.ai_config.get('TIMEOUT', 120)}, "
            f"max_tokens={self.ai_config.get('MAX_TOKENS', 5000)}"
        )

        if not self.client.config.api_key:
            return AIAnalysisResult(
                success=False,
                error="未配置 AI API Key，请在 config.yaml 或环境变量 AI_API_KEY 中设置",
            )

        news_content, hotlist_total, analyzed_count = self._prepare_news_content(stats)
        if not news_content:
            return AIAnalysisResult(
                success=False,
                skipped=True,
                error="没有可供分析的热榜内容，跳过 AI 分析",
                total_news=hotlist_total,
                hotlist_count=hotlist_total,
                analyzed_news=0,
                max_news_limit=self.max_news,
            )

        if not keywords:
            keywords = [stat.get("word", "") for stat in stats if stat.get("word")]

        current_time = self.get_time_func().strftime("%Y-%m-%d %H:%M:%S")
        user_prompt = self.user_prompt_template
        user_prompt = user_prompt.replace("{report_mode}", report_mode)
        user_prompt = user_prompt.replace("{report_type}", report_type)
        user_prompt = user_prompt.replace("{current_time}", current_time)
        user_prompt = user_prompt.replace("{news_count}", str(hotlist_total))
        user_prompt = user_prompt.replace("{platforms}", ", ".join(platforms or []) or "未指定")
        user_prompt = user_prompt.replace("{keywords}", ", ".join((keywords or [])[:20]) or "-")
        user_prompt = user_prompt.replace("{news_content}", news_content)
        user_prompt = user_prompt.replace("{language}", self.language)

        standalone_content = ""
        if self.include_standalone and standalone_data:
            standalone_content = self._prepare_standalone_content(standalone_data)
        user_prompt = user_prompt.replace("{standalone_content}", standalone_content)

        if self.debug:
            print("\n" + "=" * 80)
            print("[AI 调试] 即将发送 AI 请求")
            print("=" * 80)
            if self.system_prompt:
                print("\n--- System Prompt ---")
                print(self.system_prompt)
            print("\n--- User Prompt ---")
            print(user_prompt)
            print("=" * 80 + "\n")

        try:
            response = self._call_ai(user_prompt)
            result = self._parse_response(response)

            if result.error and "JSON 解析失败" in result.error:
                print("[AI] JSON 解析失败，尝试修复...")
                retry_result = self._retry_fix_json(response, result.error)
                if retry_result and retry_result.success and not retry_result.error:
                    retry_result.raw_response = response
                    result = retry_result
                    print("[AI] JSON 修复成功")
                else:
                    print("[AI] JSON 修复失败，保留原始结果")

            if not self.include_standalone:
                result.standalone_summaries = {}

            result.total_news = hotlist_total
            result.hotlist_count = hotlist_total
            result.analyzed_news = analyzed_count
            result.max_news_limit = self.max_news
            return result
        except Exception as exc:
            error_type = type(exc).__name__
            error_msg = str(exc)
            if len(error_msg) > 200:
                error_msg = error_msg[:200] + "..."
            return AIAnalysisResult(
                success=False,
                error=f"AI 调用失败 ({error_type}): {error_msg}",
            )

    def _prepare_news_content(self, stats: List[Dict]) -> Tuple[str, int, int]:
        """Serialize hotlist statistics into the prompt payload."""

        lines: List[str] = []
        hotlist_total = sum(len(stat.get("titles", [])) for stat in stats or [])
        analyzed_count = 0

        for stat in stats or []:
            word = str(stat.get("word", "")).strip()
            titles = stat.get("titles", [])
            if not word or not titles:
                continue

            section_lines: List[str] = []
            for item in titles:
                if analyzed_count >= self.max_news:
                    break
                if not isinstance(item, dict):
                    continue

                title = str(item.get("title", "")).strip()
                if not title:
                    continue

                source = str(item.get("source_name", item.get("source", ""))).strip()
                prefix = f"- [{source}] {title}" if source else f"- {title}"

                meta_parts: List[str] = []
                rank_range = self._format_rank_range(item.get("ranks", []))
                if rank_range:
                    meta_parts.append(f"排名:{rank_range}")

                time_range = self._format_time_range(
                    item.get("first_time", ""),
                    item.get("last_time", ""),
                    fallback=item.get("time_display", ""),
                )
                if time_range:
                    meta_parts.append(f"时间:{time_range}")

                count = item.get("count", 1)
                if count and count > 1:
                    meta_parts.append(f"次数:{count}次")

                if self.include_rank_timeline:
                    timeline = self._format_rank_timeline(item.get("rank_timeline", []))
                    if timeline:
                        meta_parts.append(f"轨迹:{timeline}")

                line = prefix
                if meta_parts:
                    line += " | " + " | ".join(meta_parts)
                section_lines.append(line)
                analyzed_count += 1

            if section_lines:
                lines.append(f"## {word} ({len(titles)}条)")
                lines.extend(section_lines)
                lines.append("")

            if analyzed_count >= self.max_news:
                break

        return "\n".join(lines).strip(), hotlist_total, analyzed_count

    def _prepare_standalone_content(self, standalone_data: Dict) -> str:
        """Serialize standalone hotlist platforms into the prompt payload."""

        lines: List[str] = []
        for platform in standalone_data.get("platforms", []):
            platform_name = str(platform.get("name", platform.get("id", ""))).strip()
            items = platform.get("items", [])
            if not platform_name or not items:
                continue

            lines.append(f"### [{platform_name}]")
            for item in items:
                title = str(item.get("title", "")).strip()
                if not title:
                    continue

                line = f"- {title}"
                meta_parts: List[str] = []
                rank_range = self._format_rank_range(item.get("ranks", []))
                if rank_range:
                    meta_parts.append(f"排名:{rank_range}")
                time_range = self._format_time_range(
                    item.get("first_time", ""),
                    item.get("last_time", ""),
                    fallback=item.get("time_display", ""),
                )
                if time_range:
                    meta_parts.append(f"时间:{time_range}")
                count = item.get("count", 1)
                if count and count > 1:
                    meta_parts.append(f"次数:{count}次")
                if self.include_rank_timeline:
                    timeline = self._format_rank_timeline(item.get("rank_timeline", []))
                    if timeline:
                        meta_parts.append(f"轨迹:{timeline}")
                if meta_parts:
                    line += " | " + " | ".join(meta_parts)
                lines.append(line)
            lines.append("")

        return "\n".join(lines).strip()

    def _call_ai(self, user_prompt: str) -> str:
        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.append({"role": "user", "content": user_prompt})
        return self.client.chat(messages)

    def _retry_fix_json(self, original_response: str, error_msg: str) -> Optional[AIAnalysisResult]:
        messages = [
            {
                "role": "system",
                "content": (
                    "你是 JSON 修复助手。请将输入内容修复为合法 JSON，"
                    "不要添加解释，只返回 JSON 对象本身。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"JSON 解析失败\n\n错误: {error_msg}\n\n"
                    f"原始响应:\n{original_response}\n\n"
                    "请直接返回修复后的 JSON，不要输出额外说明。"
                ),
            },
        ]

        try:
            response = self.client.chat(messages)
            return self._parse_response(response)
        except Exception as exc:
            print(f"[AI] JSON 修复请求失败: {type(exc).__name__}: {exc}")
            return None

    def _parse_response(self, response: str) -> AIAnalysisResult:
        result = AIAnalysisResult(raw_response=response)
        if not response or not response.strip():
            result.error = "AI 返回为空"
            return result

        json_str = self._extract_json_block(response)
        if not json_str:
            result.error = "未提取到 JSON 内容"
            result.core_trends = response[:500] + "..." if len(response) > 500 else response
            result.success = True
            return result

        data = None
        parse_error = None
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as exc:
            parse_error = exc

        if data is None:
            try:
                from json_repair import repair_json

                repaired = repair_json(json_str, return_objects=True)
                if isinstance(repaired, dict):
                    data = repaired
                    print("[AI] 已使用 json_repair 修复 JSON 响应")
            except Exception:
                pass

        if data is None:
            if parse_error is not None:
                context = json_str[max(0, parse_error.pos - 30): parse_error.pos + 30]
                result.error = f"JSON 解析失败 (位置 {parse_error.pos}): {parse_error.msg}"
                if context:
                    result.error += f"；上下文: ...{context}..."
            else:
                result.error = "JSON 解析失败"
            result.core_trends = json_str[:500] + "..." if len(json_str) > 500 else json_str
            result.success = True
            return result

        try:
            result.core_trends = str(data.get("core_trends", ""))
            result.sentiment_controversy = str(data.get("sentiment_controversy", ""))
            result.signals = str(data.get("signals", ""))
            result.outlook_strategy = str(data.get("outlook_strategy", ""))

            summaries = data.get("standalone_summaries", {})
            if isinstance(summaries, dict):
                result.standalone_summaries = {
                    str(key): str(value)
                    for key, value in summaries.items()
                    if str(key).strip() and str(value).strip()
                }

            result.success = True
        except Exception as exc:
            result.error = f"结果字段解析失败: {type(exc).__name__}: {exc}"
            result.core_trends = json_str[:500] + "..." if len(json_str) > 500 else json_str
            result.success = True

        return result

    @staticmethod
    def _extract_json_block(response: str) -> str:
        text = response.strip()
        if "```json" in text:
            text = text.split("```json", 1)[1]
            text = text.split("```", 1)[0]
        elif text.startswith("```") and text.count("```") >= 2:
            text = text.split("```", 2)[1]
        return text.strip()

    @staticmethod
    def _format_rank_range(ranks: List[int]) -> str:
        if not ranks:
            return ""
        ordered = sorted(rank for rank in ranks if isinstance(rank, int) and rank > 0)
        if not ordered:
            return ""
        return str(ordered[0]) if ordered[0] == ordered[-1] else f"{ordered[0]}-{ordered[-1]}"

    @staticmethod
    def _format_time_range(first_time: str, last_time: str, fallback: str = "") -> str:
        if fallback:
            return str(fallback).replace("[", "").replace("]", "").replace(" ~ ", "~")

        def _extract(value: str) -> str:
            if not value:
                return ""
            value = str(value)
            if " " in value:
                value = value.split(" ", 1)[1]
            value = value.replace("-", ":")
            return value[:5] if ":" in value and len(value) >= 5 else value

        first_display = _extract(first_time)
        last_display = _extract(last_time)
        if first_display and last_display and first_display != last_display:
            return f"{first_display}~{last_display}"
        return first_display or last_display

    @staticmethod
    def _format_rank_timeline(rank_timeline: List[Dict[str, Any]]) -> str:
        parts: List[str] = []
        for point in rank_timeline or []:
            time_value = str(point.get("time", "")).replace("-", ":")
            rank_value = point.get("rank")
            if not time_value:
                continue
            rank_text = "无" if rank_value in (None, 0) else str(rank_value)
            parts.append(f"{rank_text}({time_value})")
        return " -> ".join(parts)
