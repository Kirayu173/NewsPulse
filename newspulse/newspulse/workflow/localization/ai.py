# coding=utf-8
"""AI-based localization strategy."""

from __future__ import annotations

from typing import Any, Dict

from newspulse.ai import AITranslator
from newspulse.ai.translator import BatchTranslationResult
from newspulse.workflow.localization.models import LocalizationTextEntry
from newspulse.workflow.shared.contracts import LocalizedReport, RenderableReport
from newspulse.workflow.shared.options import LocalizationOptions


class AILocalizationStrategy:
    """Translate report content into the target language for downstream rendering."""

    def __init__(
        self,
        *,
        translator: AITranslator | Any | None = None,
        translation_config: Dict[str, Any] | None = None,
        ai_config: Dict[str, Any] | None = None,
    ):
        self.translation_config = dict(translation_config or {})
        self.ai_config = dict(ai_config or {})
        self.translator = translator or AITranslator(self.translation_config, self.ai_config)

    def run(self, report: RenderableReport, options: LocalizationOptions) -> LocalizedReport:
        if hasattr(self.translator, "target_language"):
            self.translator.target_language = options.language
        if hasattr(self.translator, "scope"):
            self.translator.scope = {
                "HOTLIST": options.scope.selection_titles or options.scope.new_items,
                "STANDALONE": options.scope.standalone,
                "INSIGHT": options.scope.insight_sections,
            }

        localized_titles: Dict[str, str] = {}
        localized_sections: Dict[str, str] = {}

        title_entries = self._collect_title_entries(report, options)
        section_entries = self._collect_section_entries(report, options)
        title_batch = self._translate_entries(title_entries)
        section_batch = self._translate_entries(section_entries)

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
            "section_success_count": section_batch.success_count,
            "section_fail_count": section_batch.fail_count,
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

    def _translate_entries(self, entries: list[LocalizationTextEntry]) -> BatchTranslationResult:
        if not entries:
            return BatchTranslationResult(total_count=0)
        texts = [entry.text for entry in entries]
        return self.translator.translate_batch(texts)

    @staticmethod
    def _iter_successful_translations(
        entries: list[LocalizationTextEntry],
        batch_result: BatchTranslationResult,
    ):
        for index, entry in enumerate(entries):
            if index >= len(batch_result.results):
                continue
            result = batch_result.results[index]
            if not result.success:
                continue
            yield entry, result.translated_text

    @staticmethod
    def _collect_errors(batch_result: BatchTranslationResult) -> list[str]:
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
