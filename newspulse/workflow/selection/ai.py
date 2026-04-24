# coding=utf-8
"""AI-based quality-gate selection strategy."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from newspulse.core.config_paths import resolve_ai_interests_path
from newspulse.workflow.selection.ai_classifier import AIBatchClassifier
from newspulse.workflow.selection.catalog import parse_topic_catalog
from newspulse.workflow.selection.context_builder import build_selection_context
from newspulse.workflow.selection.keyword import KeywordSelectionStrategy
from newspulse.workflow.selection.models import AIBatchNewsItem, AIQualityDecision, SelectionTopic
from newspulse.workflow.selection.pipeline import SelectionPipelineProjector
from newspulse.workflow.selection.semantic import SemanticSelectionLayer
from newspulse.workflow.shared.ai_runtime.client import AIRuntimeClient, AIRuntimeConfig, CachedAIRuntimeClient
from newspulse.workflow.shared.ai_runtime.embedding import EmbeddingRuntimeClient
from newspulse.workflow.shared.ai_runtime.prompts import PromptTemplate, load_prompt_template
from newspulse.workflow.shared.ai_runtime.provider_env import resolve_embedding_env_defaults
from newspulse.workflow.shared.ai_runtime.request_config import build_request_overrides, resolve_runtime_cache_config
from newspulse.workflow.shared.contracts import SelectionResult
from newspulse.workflow.shared.options import SelectionOptions


class AISelectionStrategy:
    """Run the native selection funnel: rule filter -> semantic filter -> LLM gate."""

    def __init__(
        self,
        *,
        storage_manager: Any,
        ai_runtime_config: Mapping[str, Any] | None = None,
        filter_config: Mapping[str, Any] | None = None,
        config_root: str | Path | None = None,
        debug: bool = False,
        client: AIRuntimeClient | Any | None = None,
        embedding_runtime_config: Mapping[str, Any] | None = None,
        embedding_client: EmbeddingRuntimeClient | Any | None = None,
        semantic_selector: SemanticSelectionLayer | None = None,
        keyword_strategy: KeywordSelectionStrategy | None = None,
        sleep_func: Callable[[float], None] | None = None,
        classify_prompt: PromptTemplate | None = None,
    ):
        self.storage_manager = storage_manager
        self.filter_config = dict(filter_config or {})
        self.config_root = Path(config_root) if config_root is not None else None
        self.debug = debug
        self.sleep_func = sleep_func or (lambda _: None)
        self.ai_runtime_config = dict(ai_runtime_config or {})

        if client is None:
            if ai_runtime_config is None:
                raise ValueError("AI runtime config is required when no client is provided")
            client = AIRuntimeClient(ai_runtime_config)
        self.client = self._wrap_runtime_cache(client)

        self.classify_prompt = classify_prompt or load_prompt_template(
            self.filter_config.get("PROMPT_FILE", "prompt.txt"),
            config_root=self.config_root,
            config_subdir="ai_filter",
            required=True,
        )
        self.request_overrides = self._build_request_overrides()
        self.classifier = AIBatchClassifier(
            storage_manager=self.storage_manager,
            client=self.client,
            classify_prompt=self.classify_prompt,
            request_overrides=self.request_overrides,
            sleep_func=self.sleep_func,
        )
        self.projector = SelectionPipelineProjector()
        self.semantic_selector = semantic_selector or self._build_semantic_selector(
            embedding_runtime_config=embedding_runtime_config,
            embedding_client=embedding_client,
        )
        self.keyword_strategy = keyword_strategy or KeywordSelectionStrategy(config_root=str(self.config_root) if self.config_root else None)

    def run(self, snapshot: Any, options: SelectionOptions) -> SelectionResult:
        """Run AI selection against the provided snapshot."""

        interests_file = options.ai.interests_file or self.filter_config.get("INTERESTS_FILE") or "ai_interests.txt"
        interests_content = self.load_interests_content(interests_file)
        if not interests_content:
            raise ValueError("No AI interests content is available for selection")

        rule_result = self.keyword_strategy.filter_items(
            snapshot.items,
            frequency_file=options.frequency_file,
        )
        topics = self.build_focus_topics(interests_content)
        semantic_result = self.semantic_selector.select(
            rule_result.passed_items,
            topics,
            options.semantic,
        )

        batch_items = self.classifier.build_batch_items(semantic_result.passed_items)
        llm_decisions = self.classifier.classify_pending_items(
            pending_items=batch_items,
            interests_content=interests_content,
            focus_topics=[topic.label for topic in topics],
            options=options,
        )

        result = self.projector.build_selection_result(
            snapshot=snapshot,
            rule_result=rule_result,
            semantic_result=semantic_result,
            llm_decisions=llm_decisions,
            llm_min_score=options.ai.min_score,
        )
        result.diagnostics.update(
            {
                "mode": snapshot.mode,
                "interests_file": interests_file,
                "focus_topic_count": len(topics),
                "focus_labels": [topic.label for topic in topics],
                "processed_candidates": len(snapshot.items),
                "rule_passed_count": len(rule_result.passed_items),
                "rule_rejected_count": len(rule_result.rejected_items),
                "semantic_passed_count": len(semantic_result.passed_items),
                "semantic_rejected_count": len(semantic_result.rejected_items),
                "llm_batch_count": len(batch_items),
                "llm_decision_count": len(llm_decisions),
                "batch_size": options.ai.batch_size,
                "batch_interval": options.ai.batch_interval,
                "min_score": options.ai.min_score,
                "semantic_candidate_count": len(semantic_result.candidates),
            }
        )
        result.diagnostics.update(
            {
                f"semantic_{key}": value
                for key, value in semantic_result.diagnostics.items()
            }
        )
        result.diagnostics.update(
            {
                "semantic_topics": [
                    {
                        "topic_id": topic.topic_id,
                        "label": topic.label,
                        "description": topic.description,
                        "priority": topic.priority,
                        "seed_keywords": list(topic.seed_keywords),
                        "negative_keywords": list(topic.negative_keywords),
                        "source": topic.source,
                    }
                    for topic in semantic_result.topics
                ],
                "semantic_candidates": [
                    {
                        **{
                            "news_item_id": candidate.news_item.news_item_id,
                            "source_id": candidate.news_item.source_id,
                            "source_name": candidate.news_item.source_name,
                            "title": candidate.news_item.title,
                            "summary": candidate.news_item.summary,
                            "current_rank": candidate.news_item.current_rank,
                            "metadata": dict(candidate.news_item.metadata or {}),
                        },
                        "topic_id": candidate.topic_id,
                        "topic_label": candidate.topic_label,
                        "score": round(candidate.score, 6),
                        "source_layers": list(candidate.source_layers),
                        "evidence": dict(candidate.evidence),
                        "context_lines": list(build_selection_context(candidate.news_item).attributes),
                    }
                    for candidate in semantic_result.candidates
                ],
                "llm_decisions": [
                    {
                        "news_item_id": decision.news_item_id,
                        "keep": decision.keep,
                        "quality_score": round(decision.quality_score, 6),
                        "reasons": list(decision.reasons),
                        "evidence": decision.evidence,
                        "matched_topics": list(decision.matched_topics),
                        "metadata": dict(decision.metadata),
                    }
                    for decision in llm_decisions
                ],
                "rule_rejections": [
                    {
                        "news_item_id": rejected.news_item_id,
                        "title": rejected.title,
                        "source_id": rejected.source_id,
                        "rejected_reason": rejected.rejected_reason,
                        "metadata": dict(rejected.metadata),
                    }
                    for rejected in rule_result.rejected_items
                ],
                "semantic_rejections": [
                    {
                        "news_item_id": rejected.news_item_id,
                        "title": rejected.title,
                        "source_id": rejected.source_id,
                        "rejected_reason": rejected.rejected_reason,
                        "score": rejected.score,
                        "metadata": dict(rejected.metadata),
                    }
                    for rejected in semantic_result.rejected_items
                ],
            }
        )
        return result

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

    @staticmethod
    def build_focus_topics(interests_content: str) -> list[SelectionTopic]:
        """Parse or synthesize semantic focus topics from interests content."""

        topics = parse_topic_catalog(interests_content)
        if topics:
            return topics
        normalized = str(interests_content or "").strip()
        if not normalized:
            return []
        return [
            SelectionTopic(
                topic_id=1,
                label="Selection Focus",
                description=normalized,
                priority=1,
                source="interests_text",
            )
        ]

    def classify_batch(
        self,
        batch_items: Sequence[AIBatchNewsItem],
        interests_content: str = "",
    ) -> list[AIQualityDecision]:
        """Classify one AI batch and recursively split on transient failures."""

        return self.classifier.classify_batch(
            batch_items,
            interests_content=interests_content,
        )

    def _build_semantic_selector(
        self,
        *,
        embedding_runtime_config: Mapping[str, Any] | None,
        embedding_client: EmbeddingRuntimeClient | Any | None,
    ) -> SemanticSelectionLayer:
        client = embedding_client
        if client is None and embedding_runtime_config:
            client = EmbeddingRuntimeClient(embedding_runtime_config)
        return SemanticSelectionLayer(embedding_client=client)

    def _build_request_overrides(self) -> dict[str, Any]:
        return build_request_overrides(
            self.filter_config,
            prompt_template=self.classify_prompt,
            operation="selection",
            prompt_name="classify",
        )

    def _wrap_runtime_cache(self, client: AIRuntimeClient | Any) -> AIRuntimeClient | Any:
        if isinstance(client, CachedAIRuntimeClient):
            return client
        if not isinstance(client, AIRuntimeClient):
            return client
        cache_config = resolve_runtime_cache_config(self.filter_config)
        if not cache_config:
            return client
        return CachedAIRuntimeClient(
            client,
            enabled=bool(cache_config.get("ENABLED", True)),
            ttl_seconds=int(cache_config.get("TTL_SECONDS", 3600) or 3600),
            max_entries=int(cache_config.get("MAX_ENTRIES", 512) or 512),
        )


def build_embedding_runtime_config(
    ai_runtime_config: Mapping[str, Any] | None,
    embedding_model: str | None = None,
) -> dict[str, Any]:
    """Derive a same-provider embedding runtime config from the filter LLM config."""

    base = dict(ai_runtime_config or {})
    env_defaults = resolve_embedding_env_defaults(
        provider_family=base.get("PROVIDER_FAMILY", "openai"),
        api_base=base.get("API_BASE", ""),
        model=embedding_model or base.get("MODEL", ""),
    )
    model = str(
        embedding_model
        or os.environ.get("AI_EMBEDDING_MODEL")
        or os.environ.get("EMB_MODEL")
        or env_defaults.get("MODEL", "")
        or ""
    ).strip()
    if not model:
        return {}
    api_base = str(
        os.environ.get("AI_EMBEDDING_API_BASE")
        or os.environ.get("AI_EMBEDDING_BASE_URL")
        or env_defaults.get("API_BASE", "")
        or base.get("API_BASE", "")
        or ""
    )
    api_key = str(
        os.environ.get("AI_EMBEDDING_API_KEY")
        or env_defaults.get("API_KEY", "")
        or base.get("API_KEY", "")
        or ""
    )
    derived = {
        "MODEL": AIRuntimeConfig.normalize_model(model, api_base, "openai"),
        "API_KEY": api_key,
        "API_BASE": api_base,
        "PROVIDER_FAMILY": "openai",
        "TIMEOUT": base.get("TIMEOUT", 120),
    }
    extra_params = base.get("EXTRA_PARAMS")
    if isinstance(extra_params, Mapping):
        derived["EXTRA_PARAMS"] = dict(extra_params)
    return derived
