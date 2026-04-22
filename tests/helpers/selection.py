from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Iterable, Mapping, Sequence


def default_quality_rules() -> list[dict[str, Any]]:
    return [
        {
            "contains": ("openai", "agent"),
            "keep": True,
            "score": 0.95,
            "reasons": ["high information gain", "important agent release"],
            "evidence": "OpenAI coding-agent news matches the configured focus.",
            "matched_topics": ["AI Agent / MCP"],
        },
        {
            "contains": ("github", "open source"),
            "keep": True,
            "score": 0.82,
            "reasons": ["notable open-source release"],
            "evidence": "Developer tooling updates are relevant to the review set.",
            "matched_topics": ["Open Source / GitHub / HN"],
        },
    ]


class DeterministicQualityAIClient:
    def __init__(
        self,
        rules: Sequence[Mapping[str, Any]] | None = None,
        *,
        default_decision: Mapping[str, Any] | None = None,
    ):
        self.classify_calls = 0
        self.rules = [dict(rule) for rule in (rules or default_quality_rules())]
        self.default_decision = dict(
            default_decision
            or {
                "keep": False,
                "score": 0.12,
                "reasons": ["low review value"],
                "evidence": "The item does not match the configured deep-analysis focus.",
                "matched_topics": [],
            }
        )

    def chat(self, messages, **kwargs):
        self.classify_calls += 1
        user_content = messages[-1]["content"]
        results = []
        for line in user_content.splitlines():
            if not line[:1].isdigit() or ". [" not in line:
                continue
            prompt_id = int(line.split(".", 1)[0])
            lowered = line.lower()
            decision = self._match_rule(lowered)
            results.append({"id": prompt_id, **decision})
        return json.dumps(results)

    def _match_rule(self, lowered_line: str) -> dict[str, Any]:
        for rule in self.rules:
            needles = [str(value).lower() for value in rule.get("contains", [])]
            if needles and any(needle in lowered_line for needle in needles):
                return {
                    "keep": bool(rule.get("keep", False)),
                    "score": float(rule.get("score", 0.0) or 0.0),
                    "reasons": list(rule.get("reasons", [])),
                    "evidence": str(rule.get("evidence", "") or ""),
                    "matched_topics": list(rule.get("matched_topics", [])),
                }
        return {
            "keep": bool(self.default_decision.get("keep", False)),
            "score": float(self.default_decision.get("score", 0.0) or 0.0),
            "reasons": list(self.default_decision.get("reasons", [])),
            "evidence": str(self.default_decision.get("evidence", "") or ""),
            "matched_topics": list(self.default_decision.get("matched_topics", [])),
        }


class FakeEmbeddingClient:
    def __init__(
        self,
        groups: Sequence[tuple[Iterable[str], Sequence[float]]] | None = None,
        *,
        default_vector: Sequence[float] = (0.0, 0.0, 1.0),
        model: str = "openai/embedding-test",
    ):
        self.groups = [
            ([str(keyword).lower() for keyword in keywords], [float(value) for value in vector])
            for keywords, vector in (
                groups
                or [
                    (("agent", "openai"), (1.0, 0.0, 0.0)),
                    (("open source", "github"), (0.0, 1.0, 0.0)),
                ]
            )
        ]
        self.default_vector = [float(value) for value in default_vector]
        self.config = SimpleNamespace(model=model)

    def is_enabled(self):
        return True

    def embed_texts(self, texts, **kwargs):
        vectors = []
        for text in texts:
            lowered = str(text).lower()
            vector = self.default_vector
            for keywords, candidate in self.groups:
                if any(keyword in lowered for keyword in keywords):
                    vector = candidate
                    break
            vectors.append(list(vector))
        return vectors
