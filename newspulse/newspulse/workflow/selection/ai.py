# coding=utf-8
"""AI-based selection strategy."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from newspulse.core.config_paths import resolve_ai_interests_path
from newspulse.workflow.selection.models import AIActiveTag, AIBatchNewsItem, AIClassificationResult
from newspulse.workflow.shared.ai_runtime.client import AIRuntimeClient
from newspulse.workflow.shared.ai_runtime.codec import decode_json_response
from newspulse.workflow.shared.ai_runtime.prompts import PromptTemplate, load_prompt_template
from newspulse.workflow.shared.contracts import HotlistItem, SelectionGroup, SelectionResult
from newspulse.workflow.shared.options import SelectionOptions


class AISelectionStrategy:
    """Run the native AI selection stage against a workflow snapshot."""

    def __init__(
        self,
        *,
        storage_manager: Any,
        ai_runtime_config: Mapping[str, Any] | None = None,
        filter_config: Mapping[str, Any] | None = None,
        config_root: str | Path | None = None,
        debug: bool = False,
        client: AIRuntimeClient | Any | None = None,
        completion_func: Callable[..., Any] | None = None,
        sleep_func: Callable[[float], None] | None = None,
        classify_prompt: PromptTemplate | None = None,
        extract_prompt: PromptTemplate | None = None,
        update_tags_prompt: PromptTemplate | None = None,
    ):
        self.storage_manager = storage_manager
        self.filter_config = dict(filter_config or {})
        self.config_root = Path(config_root) if config_root is not None else None
        self.debug = debug
        self.sleep_func = sleep_func or time.sleep

        if client is None:
            if ai_runtime_config is None:
                raise ValueError("AI runtime config is required when no client is provided")
            client = AIRuntimeClient(ai_runtime_config, completion_func=completion_func)
        self.client = client

        self.classify_prompt = classify_prompt or load_prompt_template(
            self.filter_config.get("PROMPT_FILE", "prompt.txt"),
            config_root=self.config_root,
            config_subdir="ai_filter",
            required=True,
        )
        self.extract_prompt = extract_prompt or load_prompt_template(
            self.filter_config.get("EXTRACT_PROMPT_FILE", "extract_prompt.txt"),
            config_root=self.config_root,
            config_subdir="ai_filter",
            required=True,
        )
        self.update_tags_prompt = update_tags_prompt or load_prompt_template(
            self.filter_config.get("UPDATE_TAGS_PROMPT_FILE", "update_tags_prompt.txt"),
            config_root=self.config_root,
            config_subdir="ai_filter",
            required=False,
        )
        self.request_overrides = self._build_request_overrides()
        self.reclassify_threshold = self._coerce_float(
            self.filter_config.get("RECLASSIFY_THRESHOLD", 0.6),
            default=0.6,
        )

    def run(self, snapshot: Any, options: SelectionOptions) -> SelectionResult:
        """Run AI selection against the provided snapshot."""

        interests_file = options.ai.interests_file or self.filter_config.get("INTERESTS_FILE") or "ai_interests.txt"
        interests_content = self.load_interests_content(options.ai.interests_file or self.filter_config.get("INTERESTS_FILE"))
        if not interests_content:
            raise ValueError("No AI interests content is available for selection")

        current_hash = self.compute_interests_hash(interests_content, interests_file)
        batch_items = self._build_batch_items(snapshot.items)

        self.storage_manager.begin_batch()
        try:
            active_tags, tag_refresh_mode = self._ensure_active_tags(interests_content, interests_file, current_hash)
            analyzed_ids = self._load_analyzed_news_ids(interests_file)
            pending_items = [
                item for item in batch_items if item.persisted_news_id is None or item.persisted_news_id not in analyzed_ids
            ]
            in_memory_results = self._classify_pending_items(pending_items, active_tags, interests_content, options)
            persisted_results = self._load_active_results(interests_file)
        finally:
            self.storage_manager.end_batch()

        result = self._build_selection_result(
            snapshot=snapshot,
            active_tags=active_tags,
            persisted_results=persisted_results,
            in_memory_results=in_memory_results,
            min_score=options.ai.min_score,
            priority_sort_enabled=options.priority_sort_enabled,
        )
        result.diagnostics.update(
            {
                "mode": snapshot.mode,
                "interests_file": interests_file,
                "active_tag_count": len(active_tags),
                "pending_candidates": len(
                    [item for item in batch_items if item.persisted_news_id is None or item.persisted_news_id not in analyzed_ids]
                ),
                "processed_candidates": len(batch_items),
                "batch_size": options.ai.batch_size,
                "batch_interval": options.ai.batch_interval,
                "min_score": options.ai.min_score,
                "tag_refresh_mode": tag_refresh_mode,
            }
        )
        return result

    @staticmethod
    def compute_interests_hash(interests_content: str, filename: str = "ai_interests.txt") -> str:
        """Compute the compatibility prompt hash for an interests file."""

        lines: list[str] = []
        for raw_line in interests_content.strip().splitlines():
            line = raw_line.strip()
            if line and not line.startswith("#"):
                lines.append(line)
        normalized = "\n".join(lines)
        content_hash = hashlib.md5(normalized.encode("utf-8")).hexdigest()
        return f"{filename}:{content_hash}"

    def load_interests_content(self, interests_file: str | None = None) -> str | None:
        """Load the AI interests file from the project-owned config tree."""

        interests_path = resolve_ai_interests_path(
            interests_file,
            config_root=self.config_root,
        )
        if not interests_path.exists():
            return None

        content = interests_path.read_text(encoding="utf-8").strip()
        return content or None

    def extract_tags(self, interests_content: str) -> list[dict[str, Any]]:
        """Extract normalized tags from the user interests description."""

        user_prompt = self._render_user_prompt(
            self.extract_prompt,
            {"interests_content": interests_content},
        )
        response = self.client.chat(self.extract_prompt.build_messages(user_prompt), **self.request_overrides)
        payload = decode_json_response(response)
        if not isinstance(payload, dict):
            return []
        return self._normalize_tag_entries(payload.get("tags", []))

    def update_tags(
        self,
        old_tags: Sequence[AIActiveTag | Mapping[str, Any]],
        interests_content: str,
    ) -> dict[str, Any] | None:
        """Ask the model how to update the existing active tag set."""

        if self.update_tags_prompt.is_empty:
            return None

        serialized_tags = []
        for tag in old_tags:
            tag_name = str(tag.tag if isinstance(tag, AIActiveTag) else tag.get("tag", "")).strip()
            if not tag_name:
                continue
            description = tag.description if isinstance(tag, AIActiveTag) else str(tag.get("description", "")).strip()
            serialized_tags.append({"tag": tag_name, "description": description})

        user_prompt = self._render_user_prompt(
            self.update_tags_prompt,
            {
                "old_tags_json": json.dumps(serialized_tags, ensure_ascii=False, indent=2),
                "interests_content": interests_content,
            },
        )
        response = self.client.chat(self.update_tags_prompt.build_messages(user_prompt), **self.request_overrides)
        payload = decode_json_response(response)
        if not isinstance(payload, dict):
            return None

        keep = self._normalize_tag_entries(payload.get("keep", []))
        add = self._normalize_tag_entries(payload.get("add", []))
        remove = []
        for raw_name in payload.get("remove", []):
            name = str(raw_name).strip()
            if name and name not in remove:
                remove.append(name)

        change_ratio = self._coerce_float(payload.get("change_ratio", 0.0), default=0.0)
        change_ratio = max(0.0, min(1.0, change_ratio))
        return {
            "keep": keep,
            "add": add,
            "remove": remove,
            "change_ratio": change_ratio,
        }

    def classify_batch(
        self,
        batch_items: Sequence[AIBatchNewsItem],
        active_tags: Sequence[AIActiveTag],
        interests_content: str = "",
    ) -> list[AIClassificationResult]:
        """Classify one AI batch and recursively split on transient failures."""

        if not batch_items or not active_tags or self.classify_prompt.is_empty:
            return []

        user_prompt = self._render_user_prompt(
            self.classify_prompt,
            {
                "interests_content": interests_content,
                "tags_list": self._format_tags_list(active_tags),
                "news_count": str(len(batch_items)),
                "news_list": self._format_news_list(batch_items),
            },
        )

        try:
            response = self.client.chat(self.classify_prompt.build_messages(user_prompt), **self.request_overrides)
            return self._parse_classify_response(response, batch_items, active_tags)
        except Exception:
            if len(batch_items) <= 1:
                return []

            split_index = len(batch_items) // 2
            left = self.classify_batch(batch_items[:split_index], active_tags, interests_content)
            right = self.classify_batch(batch_items[split_index:], active_tags, interests_content)
            return left + right

    def _build_request_overrides(self) -> dict[str, Any]:
        overrides: dict[str, Any] = {}
        timeout = self.filter_config.get("TIMEOUT")
        if timeout is not None:
            overrides["timeout"] = int(timeout)
        num_retries = self.filter_config.get("NUM_RETRIES")
        if num_retries is not None:
            overrides["num_retries"] = int(num_retries)
        extra_params = self.filter_config.get("EXTRA_PARAMS", {})
        if isinstance(extra_params, Mapping):
            overrides.update(extra_params)
        return overrides

    def _ensure_active_tags(
        self,
        interests_content: str,
        interests_file: str,
        current_hash: str,
    ) -> tuple[list[AIActiveTag], str]:
        active_tags = self._load_active_tags(interests_file)
        latest_hash = self.storage_manager.get_latest_prompt_hash(interests_file=interests_file)
        if not active_tags:
            self._extract_and_save_tags(interests_content, interests_file, current_hash)
            return self._load_active_tags(interests_file), "initialized"

        if latest_hash == current_hash:
            return active_tags, "reused"

        update_plan = self.update_tags(active_tags, interests_content)
        if update_plan and update_plan.get("change_ratio", 1.0) < self.reclassify_threshold:
            self._apply_incremental_tag_update(active_tags, update_plan, interests_file, current_hash)
            return self._load_active_tags(interests_file), "incremental"

        self.storage_manager.deprecate_all_ai_filter_tags(interests_file=interests_file)
        self.storage_manager.clear_analyzed_news(interests_file=interests_file)
        self._extract_and_save_tags(interests_content, interests_file, current_hash)
        return self._load_active_tags(interests_file), "replaced"

    def _extract_and_save_tags(self, interests_content: str, interests_file: str, prompt_hash: str) -> None:
        extracted_tags = self.extract_tags(interests_content)
        ordered_tags = self._with_ordered_priorities(extracted_tags)
        if not ordered_tags:
            raise ValueError("AI selection did not produce any usable tags")

        version = self.storage_manager.get_latest_ai_filter_tag_version() + 1
        saved = self.storage_manager.save_ai_filter_tags(
            ordered_tags,
            version,
            prompt_hash,
            interests_file=interests_file,
        )
        if saved <= 0:
            raise ValueError("Failed to save AI selection tags")

    def _apply_incremental_tag_update(
        self,
        active_tags: Sequence[AIActiveTag],
        update_plan: Mapping[str, Any],
        interests_file: str,
        prompt_hash: str,
    ) -> None:
        active_by_name = {tag.tag: tag for tag in active_tags}
        keep_tags = self._with_ordered_priorities(update_plan.get("keep", []), start_priority=1)
        add_tags = self._with_ordered_priorities(update_plan.get("add", []), start_priority=len(keep_tags) + 1)
        remove_names = [name for name in update_plan.get("remove", []) if name in active_by_name]

        remove_ids = [active_by_name[name].id for name in remove_names]
        if remove_ids:
            self.storage_manager.deprecate_specific_ai_filter_tags(remove_ids)

        if keep_tags:
            self.storage_manager.update_ai_filter_tag_descriptions(keep_tags, interests_file=interests_file)
            self.storage_manager.update_ai_filter_tag_priorities(keep_tags, interests_file=interests_file)

        if add_tags:
            version = self.storage_manager.get_latest_ai_filter_tag_version() + 1
            self.storage_manager.save_ai_filter_tags(
                add_tags,
                version,
                prompt_hash,
                interests_file=interests_file,
            )

        self.storage_manager.update_ai_filter_tags_hash(interests_file, prompt_hash)
        self.storage_manager.clear_unmatched_analyzed_news(interests_file=interests_file)

    def _classify_pending_items(
        self,
        pending_items: Sequence[AIBatchNewsItem],
        active_tags: Sequence[AIActiveTag],
        interests_content: str,
        options: SelectionOptions,
    ) -> list[AIClassificationResult]:
        if not pending_items or not active_tags:
            return []

        all_results: list[AIClassificationResult] = []
        batch_size = max(1, int(options.ai.batch_size or 1))
        batch_interval = max(0.0, float(options.ai.batch_interval or 0.0))

        for batch_index, start in enumerate(range(0, len(pending_items), batch_size), start=1):
            if batch_index > 1 and batch_interval > 0:
                self.sleep_func(batch_interval)

            batch = list(pending_items[start : start + batch_size])
            batch_results = self.classify_batch(batch, active_tags, interests_content)
            all_results.extend(batch_results)

            persisted_batch_results = [
                {
                    "news_item_id": result.persisted_news_id,
                    "source_type": result.source_type,
                    "tag_id": result.tag_id,
                    "relevance_score": result.relevance_score,
                }
                for result in batch_results
                if result.persisted_news_id is not None
            ]
            if persisted_batch_results:
                self.storage_manager.save_ai_filter_results(persisted_batch_results)

        persistable_news_ids = [item.persisted_news_id for item in pending_items if item.persisted_news_id is not None]
        if persistable_news_ids:
            matched_ids = {
                result.persisted_news_id
                for result in all_results
                if result.persisted_news_id is not None
            }
            self.storage_manager.save_analyzed_news(
                persistable_news_ids,
                "hotlist",
                options.ai.interests_file or self.filter_config.get("INTERESTS_FILE") or "ai_interests.txt",
                self.compute_interests_hash(
                    interests_content,
                    options.ai.interests_file or self.filter_config.get("INTERESTS_FILE") or "ai_interests.txt",
                ),
                matched_ids,
            )
        return all_results

    def _build_selection_result(
        self,
        *,
        snapshot: Any,
        active_tags: Sequence[AIActiveTag],
        persisted_results: Sequence[Mapping[str, Any]],
        in_memory_results: Sequence[AIClassificationResult],
        min_score: float,
        priority_sort_enabled: bool,
    ) -> SelectionResult:
        snapshot_items = {str(item.news_item_id): item for item in snapshot.items}
        tag_by_id = {tag.id: tag for tag in active_tags}
        best_matches = self._collect_best_matches(
            snapshot_items=snapshot_items,
            tag_by_id=tag_by_id,
            persisted_results=persisted_results,
            in_memory_results=in_memory_results,
            min_score=min_score,
        )

        groups_by_tag: dict[int, list[tuple[HotlistItem, float]]] = {}
        for news_item_id, match in best_matches.items():
            tag_id = int(match["tag_id"])
            score = float(match["relevance_score"])
            item = snapshot_items.get(news_item_id)
            if item is None:
                continue
            groups_by_tag.setdefault(tag_id, []).append((item, score))

        groups: list[SelectionGroup] = []
        for tag in active_tags:
            matched_items = groups_by_tag.get(tag.id, [])
            if not matched_items:
                continue

            matched_items.sort(key=lambda entry: (-entry[1], entry[0].current_rank or 9999, entry[0].title))
            items = [entry[0] for entry in matched_items]
            scores = [entry[1] for entry in matched_items]
            groups.append(
                SelectionGroup(
                    key=f"tag-{tag.id}",
                    label=tag.tag,
                    description=tag.description,
                    position=tag.priority,
                    items=items,
                    metadata={
                        "tag_id": tag.id,
                        "total_matched": len(items),
                        "total_selected": len(items),
                        "percentage": round(len(items) / len(snapshot.items) * 100, 2) if snapshot.items else 0,
                        "average_relevance_score": round(sum(scores) / len(scores), 4),
                    },
                )
            )

        if priority_sort_enabled:
            groups.sort(key=lambda group: (group.position, -len(group.items), group.label.lower()))
        else:
            groups.sort(key=lambda group: (-len(group.items), group.position, group.label.lower()))

        selected_items = self._flatten_selected_items(groups)
        return SelectionResult(
            strategy="ai",
            groups=groups,
            selected_items=selected_items,
            total_candidates=len(snapshot.items),
            total_selected=len(selected_items),
            diagnostics={
                "matched_candidates": len(best_matches),
                "group_count": len(groups),
            },
        )

    def _collect_best_matches(
        self,
        *,
        snapshot_items: Mapping[str, HotlistItem],
        tag_by_id: Mapping[int, AIActiveTag],
        persisted_results: Sequence[Mapping[str, Any]],
        in_memory_results: Sequence[AIClassificationResult],
        min_score: float,
    ) -> dict[str, dict[str, Any]]:
        best_matches: dict[str, dict[str, Any]] = {}

        def consider(news_item_id: str, tag_id: int, relevance_score: float) -> None:
            if news_item_id not in snapshot_items:
                return
            if tag_id not in tag_by_id:
                return
            if relevance_score < min_score:
                return

            candidate = {"tag_id": tag_id, "relevance_score": relevance_score}
            existing = best_matches.get(news_item_id)
            if existing is None:
                best_matches[news_item_id] = candidate
                return

            current_tag = tag_by_id[int(existing["tag_id"])]
            next_tag = tag_by_id[tag_id]
            if relevance_score > float(existing["relevance_score"]):
                best_matches[news_item_id] = candidate
                return
            if relevance_score == float(existing["relevance_score"]) and next_tag.priority < current_tag.priority:
                best_matches[news_item_id] = candidate

        for row in persisted_results:
            news_item_id = str(row.get("news_item_id", "")).strip()
            tag_id = self._coerce_int(row.get("tag_id"), default=None)
            if not news_item_id or tag_id is None:
                continue
            consider(news_item_id, tag_id, self._coerce_float(row.get("relevance_score"), default=0.0))

        for row in in_memory_results:
            consider(row.news_item_id, row.tag_id, row.relevance_score)

        return best_matches

    @staticmethod
    def _flatten_selected_items(groups: Sequence[SelectionGroup]) -> list[HotlistItem]:
        seen_ids: set[str] = set()
        selected_items: list[HotlistItem] = []
        for group in groups:
            for item in group.items:
                if item.news_item_id in seen_ids:
                    continue
                seen_ids.add(item.news_item_id)
                selected_items.append(item)
        return selected_items

    def _load_active_tags(self, interests_file: str) -> list[AIActiveTag]:
        rows = self.storage_manager.get_active_ai_filter_tags(interests_file=interests_file)
        tags: list[AIActiveTag] = []
        for row in rows:
            tag_name = str(row.get("tag", "")).strip()
            tag_id = self._coerce_int(row.get("id"), default=None)
            if not tag_name or tag_id is None:
                continue
            tags.append(
                AIActiveTag(
                    id=tag_id,
                    tag=tag_name,
                    description=str(row.get("description", "")).strip(),
                    priority=self._coerce_int(row.get("priority"), default=9999) or 9999,
                    version=self._coerce_int(row.get("version"), default=0) or 0,
                    prompt_hash=str(row.get("prompt_hash", "")).strip(),
                )
            )
        return tags

    def _load_analyzed_news_ids(self, interests_file: str) -> set[int]:
        raw_ids = self.storage_manager.get_analyzed_news_ids("hotlist", interests_file=interests_file)
        analyzed_ids: set[int] = set()
        for raw_id in raw_ids:
            coerced = self._coerce_int(raw_id, default=None)
            if coerced is not None:
                analyzed_ids.add(coerced)
        return analyzed_ids

    def _load_active_results(self, interests_file: str) -> list[dict[str, Any]]:
        rows = self.storage_manager.get_active_ai_filter_results(interests_file=interests_file)
        return [dict(row) for row in rows]

    def _build_batch_items(self, snapshot_items: Iterable[HotlistItem]) -> list[AIBatchNewsItem]:
        batch_items: list[AIBatchNewsItem] = []
        for prompt_id, item in enumerate(snapshot_items, start=1):
            batch_items.append(
                AIBatchNewsItem(
                    prompt_id=prompt_id,
                    news_item_id=str(item.news_item_id),
                    title=item.title,
                    source_id=item.source_id,
                    source_name=item.source_name,
                    persisted_news_id=self._coerce_int(item.news_item_id, default=None),
                )
            )
        return batch_items

    def _parse_classify_response(
        self,
        response: str,
        batch_items: Sequence[AIBatchNewsItem],
        active_tags: Sequence[AIActiveTag],
    ) -> list[AIClassificationResult]:
        payload = decode_json_response(response)
        if not isinstance(payload, list):
            return []

        item_by_prompt_id = {item.prompt_id: item for item in batch_items}
        tag_by_id = {tag.id: tag for tag in active_tags}
        best_per_news: dict[str, AIClassificationResult] = {}

        for entry in payload:
            if not isinstance(entry, Mapping):
                continue

            prompt_id = self._coerce_int(entry.get("id"), default=None)
            if prompt_id is None or prompt_id not in item_by_prompt_id:
                continue
            news_item = item_by_prompt_id[prompt_id]

            candidates = self._extract_classify_candidates(entry)
            best_candidate_tag: int | None = None
            best_candidate_score = -1.0
            for candidate in candidates:
                tag_id = self._coerce_int(candidate.get("tag_id"), default=None)
                if tag_id is None or tag_id not in tag_by_id:
                    continue
                score = self._coerce_float(candidate.get("score", 0.5), default=0.5)
                score = max(0.0, min(1.0, score))
                if score > best_candidate_score:
                    best_candidate_tag = tag_id
                    best_candidate_score = score

            if best_candidate_tag is None:
                continue

            result = AIClassificationResult(
                news_item_id=news_item.news_item_id,
                tag_id=best_candidate_tag,
                relevance_score=best_candidate_score,
                persisted_news_id=news_item.persisted_news_id,
            )

            existing = best_per_news.get(result.news_item_id)
            if existing is None:
                best_per_news[result.news_item_id] = result
                continue

            current_tag = tag_by_id[existing.tag_id]
            next_tag = tag_by_id[result.tag_id]
            if result.relevance_score > existing.relevance_score:
                best_per_news[result.news_item_id] = result
                continue
            if result.relevance_score == existing.relevance_score and next_tag.priority < current_tag.priority:
                best_per_news[result.news_item_id] = result

        return list(best_per_news.values())

    @staticmethod
    def _extract_classify_candidates(entry: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        if "tag_id" in entry:
            return [entry]

        nested_tags = entry.get("tags", [])
        if isinstance(nested_tags, list):
            return [candidate for candidate in nested_tags if isinstance(candidate, Mapping)]
        return []

    @staticmethod
    def _normalize_tag_entries(raw_entries: Any) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        seen_names: set[str] = set()
        if not isinstance(raw_entries, list):
            return normalized

        for entry in raw_entries:
            if not isinstance(entry, Mapping):
                continue
            tag_name = str(entry.get("tag", "")).strip()
            if not tag_name or tag_name in seen_names:
                continue
            normalized.append(
                {
                    "tag": tag_name,
                    "description": str(entry.get("description", "")).strip(),
                }
            )
            seen_names.add(tag_name)
        return normalized

    @staticmethod
    def _with_ordered_priorities(tags: Sequence[Mapping[str, Any]], start_priority: int = 1) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        next_priority = start_priority
        for tag in tags:
            tag_name = str(tag.get("tag", "")).strip()
            if not tag_name:
                continue
            normalized.append(
                {
                    "tag": tag_name,
                    "description": str(tag.get("description", "")).strip(),
                    "priority": next_priority,
                }
            )
            next_priority += 1
        return normalized

    @staticmethod
    def _format_tags_list(tags: Sequence[AIActiveTag]) -> str:
        return "\n".join(
            f"{tag.id}. {tag.tag}: {tag.description}".rstrip(": ")
            for tag in tags
        )

    @staticmethod
    def _format_news_list(batch_items: Sequence[AIBatchNewsItem]) -> str:
        return "\n".join(
            f"{item.prompt_id}. [{item.source_name or item.source_id}] {item.title}"
            for item in batch_items
        )

    @staticmethod
    def _render_user_prompt(template: PromptTemplate, replacements: Mapping[str, str]) -> str:
        user_prompt = template.user_prompt
        for key, value in replacements.items():
            user_prompt = user_prompt.replace("{" + key + "}", str(value))
        return user_prompt

    @staticmethod
    def _coerce_int(value: Any, default: int | None = 0) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _coerce_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
