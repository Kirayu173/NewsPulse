# coding=utf-8
"""AI translator for notification content."""

from dataclasses import dataclass, field
from typing import Any, Dict, List

from newspulse.ai.client import AIClient
from newspulse.ai.prompt_loader import load_prompt_template


@dataclass
class TranslationResult:
    translated_text: str = ""
    original_text: str = ""
    success: bool = False
    error: str = ""


@dataclass
class BatchTranslationResult:
    results: List[TranslationResult] = field(default_factory=list)
    success_count: int = 0
    fail_count: int = 0
    total_count: int = 0
    prompt: str = ""
    raw_response: str = ""
    parsed_count: int = 0


class AITranslator:
    def __init__(self, translation_config: Dict[str, Any], ai_config: Dict[str, Any]):
        self.translation_config = translation_config
        self.ai_config = ai_config
        self.enabled = translation_config.get("ENABLED", False)
        self.target_language = translation_config.get("LANGUAGE", "English")
        self.scope = translation_config.get("SCOPE", {"HOTLIST": True, "STANDALONE": True})
        self.client = AIClient(ai_config)
        self.system_prompt, self.user_prompt_template = load_prompt_template(
            translation_config.get("PROMPT_FILE", "ai_translation_prompt.txt"),
            label="翻译",
        )

    def translate(self, text: str) -> TranslationResult:
        result = TranslationResult(original_text=text)

        if not self.enabled:
            result.error = "翻译功能未启用"
            return result

        if not self.client.api_key:
            result.error = "未配置 AI API Key"
            return result

        if not text or not text.strip():
            result.translated_text = text
            result.success = True
            return result

        try:
            user_prompt = self.user_prompt_template
            user_prompt = user_prompt.replace("{target_language}", self.target_language)
            user_prompt = user_prompt.replace("{content}", text)
            result.translated_text = self._call_ai(user_prompt).strip()
            result.success = True
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            if len(error_msg) > 100:
                error_msg = error_msg[:100] + "..."
            result.error = f"翻译失败 ({error_type}): {error_msg}"

        return result

    def translate_batch(self, texts: List[str]) -> BatchTranslationResult:
        batch_result = BatchTranslationResult(total_count=len(texts))

        if not self.enabled:
            for text in texts:
                batch_result.results.append(TranslationResult(original_text=text, error="翻译功能未启用"))
            batch_result.fail_count = len(texts)
            return batch_result

        if not self.client.api_key:
            for text in texts:
                batch_result.results.append(TranslationResult(original_text=text, error="未配置 AI API Key"))
            batch_result.fail_count = len(texts)
            return batch_result

        if not texts:
            return batch_result

        non_empty_indices = []
        non_empty_texts = []
        for i, text in enumerate(texts):
            if text and text.strip():
                non_empty_indices.append(i)
                non_empty_texts.append(text)

        for text in texts:
            batch_result.results.append(TranslationResult(original_text=text))

        for i, text in enumerate(texts):
            if not text or not text.strip():
                batch_result.results[i].translated_text = text
                batch_result.results[i].success = True
                batch_result.success_count += 1

        if not non_empty_texts:
            return batch_result

        try:
            batch_content = self._format_batch_content(non_empty_texts)
            user_prompt = self.user_prompt_template
            user_prompt = user_prompt.replace("{target_language}", self.target_language)
            user_prompt = user_prompt.replace("{content}", batch_content)

            if self.system_prompt:
                batch_result.prompt = f"[system]\n{self.system_prompt}\n\n[user]\n{user_prompt}"
            else:
                batch_result.prompt = user_prompt

            response = self._call_ai(user_prompt)
            batch_result.raw_response = response
            translated_texts, raw_parsed_count = self._parse_batch_response(response, len(non_empty_texts))
            batch_result.parsed_count = raw_parsed_count

            for idx, translated in zip(non_empty_indices, translated_texts):
                batch_result.results[idx].translated_text = translated
                batch_result.results[idx].success = True
                batch_result.success_count += 1
        except Exception as e:
            error_msg = f"批量翻译失败: {type(e).__name__}: {str(e)[:100]}"
            for idx in non_empty_indices:
                batch_result.results[idx].error = error_msg
            batch_result.fail_count = len(non_empty_indices)

        return batch_result

    def _format_batch_content(self, texts: List[str]) -> str:
        return "\n".join(f"[{i}] {text}" for i, text in enumerate(texts, 1))

    def _parse_batch_response(self, response: str, expected_count: int) -> tuple:
        results = []
        lines = response.strip().split("\n")

        current_idx = None
        current_text = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("[") and "]" in stripped:
                bracket_end = stripped.index("]")
                try:
                    idx = int(stripped[1:bracket_end])
                    if current_idx is not None:
                        results.append((current_idx, "\n".join(current_text).strip()))
                    current_idx = idx
                    current_text = [stripped[bracket_end + 1:].strip()]
                except ValueError:
                    if current_idx is not None:
                        current_text.append(line)
            elif current_idx is not None:
                current_text.append(line)

        if current_idx is not None:
            results.append((current_idx, "\n".join(current_text).strip()))

        results.sort(key=lambda x: x[0])
        translated = [text for _, text in results]
        raw_parsed_count = len(translated)

        if len(translated) != expected_count:
            translated = []
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("[") and "]" in stripped:
                    bracket_end = stripped.index("]")
                    translated.append(stripped[bracket_end + 1:].strip())
                elif stripped:
                    translated.append(stripped)
            raw_parsed_count = len(translated)

        while len(translated) < expected_count:
            translated.append("")

        return translated[:expected_count], raw_parsed_count

    def _call_ai(self, user_prompt: str) -> str:
        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.append({"role": "user", "content": user_prompt})
        return self.client.chat(messages)
