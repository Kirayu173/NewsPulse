# coding=utf-8
"""AI-based localization strategy."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable

from newspulse.workflow.localization.models import (
    LocalizationBatchResult,
    LocalizationTextEntry,
    LocalizationTextResult,
)
from newspulse.workflow.shared.ai_runtime.client import AIRuntimeClient
from newspulse.workflow.shared.ai_runtime.prompts import PromptTemplate, load_prompt_template
from newspulse.workflow.shared.contracts import LocalizedReport, RenderableReport
from newspulse.workflow.shared.options import LocalizationOptions


class AILocalizationStrategy:
    """Translate report content into the target language for downstream rendering."""

    def __init__(
        self,
        *,
        translation_config: Mapping[str, Any] | None = None,
        ai_runtime_config: Mapping[str, Any] | None = None,
        config_root: str | Path | None = None,
        client: AIRuntimeClient | Any | None = None,
        completion_func: Callable[..., Any] | None = None,
        prompt_template: PromptTemplate | None = None,
    ):
        self.translation_config = dict(translation_config or {})
        self.ai_runtime_config = dict(ai_runtime_config or {})
        self.config_root = Path(config_root) if config_root is not None else None
        self.client = client or AIRuntimeClient(self.ai_runtime_config, completion_func=completion_func)
        self.prompt_template = prompt_template or load_prompt_template(
            self.translation_config.get("PROMPT_FILE", "ai_translation_prompt.txt"),
            config_root=self.config_root,
            required=False,
        )
        self.request_overrides = self._build_request_overrides()

    def run(self, report: RenderableReport, options: LocalizationOptions) -> LocalizedReport:
        localized_titles: dict[str, str] = {}
        localized_sections: dict[str, str] = {}

        title_entries = self._collect_title_entries(report, options)
        section_entries = self._collect_section_entries(report, options)
        title_batch = self._translate_entries(title_entries, target_language=options.language)
        section_batch = self._translate_entries(section_entries, target_language=options.language)

        for entry, translated in self._iter_successful_translations(title_entries, title_batch):
            localized_titles[entry.key] = translated

        for entry, translated in self._iter_successful_translations(section_entries, section_batch):
            localized_sections[entry.key] = translated

        translation_meta = {
            "enabled": True,
            "strategy": "ai",
            "language": options.language,
            "title_candidates": len(title_entries),
            "section_candidates": len(section_entries),
            "title_success_count": title_batch.success_count,
            "title_fail_count": title_batch.fail_count,
            "title_parsed_count": title_batch.parsed_count,
            "section_success_count": section_batch.success_count,
            "section_fail_count": section_batch.fail_count,
            "section_parsed_count": section_batch.parsed_count,
            "title_prompt": title_batch.prompt,
            "title_raw_response": title_batch.raw_response,
            "section_prompt": section_batch.prompt,
            "section_raw_response": section_batch.raw_response,
        }
        if not title_entries and not section_entries:
            translation_meta["skipped"] = True
            translation_meta["reason"] = "no localizable content found"

        errors = self._collect_errors(title_batch) + self._collect_errors(section_batch)
        if errors:
            translation_meta["errors"] = errors

        return LocalizedReport(
            base_report=report,
            localized_titles=localized_titles,
            localized_sections=localized_sections,
            language=options.language,
            translation_meta=translation_meta,
        )

    def _translate_entries(
        self,
        entries: list[LocalizationTextEntry],
        *,
        target_language: str,
    ) -> LocalizationBatchResult:
        if not entries:
            return LocalizationBatchResult.empty()

        texts = [entry.text for entry in entries]
        if self.prompt_template.is_empty:
            return LocalizationBatchResult.failed(texts, "translation prompt template is empty")

        results = [LocalizationTextResult(original_text=text) for text in texts]
        non_empty_indices: list[int] = []
        non_empty_texts: list[str] = []
        for index, text in enumerate(texts):
            if text and text.strip():
                non_empty_indices.append(index)
                non_empty_texts.append(text)
            else:
                results[index] = LocalizationTextResult(
                    original_text=text,
                    translated_text=text,
                    success=True,
                )

        if not non_empty_texts:
            success_count = sum(1 for result in results if result.success)
            return LocalizationBatchResult(
                results=results,
                success_count=success_count,
                fail_count=len(results) - success_count,
                total_count=len(results),
            )

        user_prompt = self._render_user_prompt(
            target_language=target_language,
            content=self._format_batch_content(non_empty_texts),
        )
        prompt_preview = self._compose_prompt_preview(user_prompt)
        raw_response = ""

        try:
            raw_response = self.client.chat(
                self.prompt_template.build_messages(user_prompt),
                **self.request_overrides,
            )
            translated_texts, parsed_count = self._parse_batch_response(raw_response, len(non_empty_texts))

            for batch_index, entry_index in enumerate(non_empty_indices):
                translated_text = translated_texts[batch_index].strip()
                if translated_text:
                    results[entry_index] = LocalizationTextResult(
                        original_text=texts[entry_index],
                        translated_text=translated_text,
                        success=True,
                    )
                else:
                    results[entry_index] = LocalizationTextResult(
                        original_text=texts[entry_index],
                        error="translation result is empty",
                    )

            success_count = sum(1 for result in results if result.success)
            return LocalizationBatchResult(
                results=results,
                success_count=success_count,
                fail_count=len(results) - success_count,
                total_count=len(results),
                prompt=prompt_preview,
                raw_response=raw_response,
                parsed_count=parsed_count,
            )
        except Exception as exc:
            error = f"batch translation failed: {type(exc).__name__}: {exc}"
            for entry_index in non_empty_indices:
                results[entry_index] = LocalizationTextResult(
                    original_text=texts[entry_index],
                    error=error,
                )

            success_count = sum(1 for result in results if result.success)
            return LocalizationBatchResult(
                results=results,
                success_count=success_count,
                fail_count=len(results) - success_count,
                total_count=len(results),
                prompt=prompt_preview,
                raw_response=raw_response,
            )

    @staticmethod
    def _iter_successful_translations(
        entries: list[LocalizationTextEntry],
        batch_result: LocalizationBatchResult,
    ):
        for index, entry in enumerate(entries):
            if index >= len(batch_result.results):
                continue
            result = batch_result.results[index]
            if not result.success:
                continue
            yield entry, result.translated_text

    @staticmethod
    def _collect_errors(batch_result: LocalizationBatchResult) -> list[str]:
        return [result.error for result in batch_result.results if result.error]

    @staticmethod
    def _collect_title_entries(report: RenderableReport, options: LocalizationOptions) -> list[LocalizationTextEntry]:
        seen: set[str] = set()
        entries: list[LocalizationTextEntry] = []

        def add_item(item: Any, kind: str) -> None:
            item_id = str(getattr(item, "news_item_id", "")).strip()
            title = str(getattr(item, "title", "")).strip()
            if not item_id or not title or item_id in seen:
                return
            seen.add(item_id)
            entries.append(LocalizationTextEntry(key=item_id, text=title, kind=kind))

        if options.scope.selection_titles:
            for group in report.selection.groups:
                for item in group.items:
                    add_item(item, "selection")

        if options.scope.new_items:
            for item in report.new_items:
                add_item(item, "new_item")

        if options.scope.standalone:
            for section in report.standalone_sections:
                for item in section.items:
                    add_item(item, "standalone")

        return entries

    @staticmethod
    def _collect_section_entries(report: RenderableReport, options: LocalizationOptions) -> list[LocalizationTextEntry]:
        if not options.scope.insight_sections:
            return []

        entries: list[LocalizationTextEntry] = []
        for section in report.insight.sections:
            content = str(section.content).strip()
            if not content:
                continue
            entries.append(LocalizationTextEntry(key=section.key, text=content, kind="insight_section"))
        return entries

    def _build_request_overrides(self) -> dict[str, Any]:
        overrides: dict[str, Any] = {}
        timeout = self.translation_config.get("TIMEOUT")
        if timeout is not None:
            overrides["timeout"] = int(timeout)
        num_retries = self.translation_config.get("NUM_RETRIES")
        if num_retries is not None:
            overrides["num_retries"] = int(num_retries)
        extra_params = self.translation_config.get("EXTRA_PARAMS", {})
        if isinstance(extra_params, Mapping):
            overrides.update(extra_params)
        return overrides

    def _render_user_prompt(self, *, target_language: str, content: str) -> str:
        user_prompt = self.prompt_template.user_prompt or "{content}"
        replacements = {
            "target_language": target_language,
            "content": content,
        }
        for key, value in replacements.items():
            user_prompt = user_prompt.replace("{" + key + "}", str(value))
        return user_prompt

    def _compose_prompt_preview(self, user_prompt: str) -> str:
        if self.prompt_template.system_prompt:
            return f"[system]\n{self.prompt_template.system_prompt}\n\n[user]\n{user_prompt}"
        return user_prompt

    @staticmethod
    def _format_batch_content(texts: list[str]) -> str:
        return "\n".join(f"[{index}] {text}" for index, text in enumerate(texts, start=1))

    @staticmethod
    def _parse_batch_response(response: str, expected_count: int) -> tuple[list[str], int]:
        results: list[tuple[int, str]] = []
        lines = (response or "").strip().splitlines()

        current_index: int | None = None
        current_text: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("[") and "]" in stripped:
                bracket_end = stripped.index("]")
                try:
                    entry_index = int(stripped[1:bracket_end])
                except ValueError:
                    if current_index is not None:
                        current_text.append(line)
                    continue

                if current_index is not None:
                    results.append((current_index, "\n".join(current_text).strip()))
                current_index = entry_index
                current_text = [stripped[bracket_end + 1 :].strip()]
            elif current_index is not None:
                current_text.append(line)

        if current_index is not None:
            results.append((current_index, "\n".join(current_text).strip()))

        results.sort(key=lambda item: item[0])
        translated = [text for _, text in results]
        parsed_count = len(translated)

        if len(translated) != expected_count:
            translated = []
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("[") and "]" in stripped:
                    bracket_end = stripped.index("]")
                    translated.append(stripped[bracket_end + 1 :].strip())
                elif stripped:
                    translated.append(stripped)
            parsed_count = len(translated)

        while len(translated) < expected_count:
            translated.append("")

        return translated[:expected_count], parsed_count
