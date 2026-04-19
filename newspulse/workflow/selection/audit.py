# coding=utf-8
"""Stage-4 audit writer for selection review artifacts."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence


REVIEW_FILE_ENCODING = "utf-8-sig"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding=REVIEW_FILE_ENCODING))


def _read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return _read_json(path)


def _selection_payload_items(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    selection = payload.get("selection")
    if not isinstance(selection, Mapping):
        return []
    items = selection.get("qualified_items") or selection.get("selected_items") or []
    return [dict(item) for item in items if isinstance(item, Mapping)]


def _selection_payload_rejections(payload: Mapping[str, Any], stage: str | None = None) -> list[dict[str, Any]]:
    selection = payload.get("selection")
    if not isinstance(selection, Mapping):
        return []
    items = selection.get("rejected_items", [])
    rows = [dict(item) for item in items if isinstance(item, Mapping)]
    if stage is None:
        return rows
    return [row for row in rows if str(row.get("rejected_stage", "")).strip() == stage]


def _load_stage4_artifacts(outbox_dir: str | Path) -> dict[str, Any]:
    outbox_path = Path(outbox_dir)
    snapshot_payload = _read_json(outbox_path / "stage4_snapshot.json")
    keyword_payload = _read_json(outbox_path / "stage4_selection_keyword.json")
    ai_payload = _read_json(outbox_path / "stage4_selection_ai.json")
    semantic_payload = _read_json_if_exists(outbox_path / "stage4_selection_semantic.json")
    llm_payload = _read_json_if_exists(outbox_path / "stage4_selection_llm.json")
    return {
        "outbox_path": outbox_path,
        "snapshot_payload": snapshot_payload,
        "keyword_payload": keyword_payload,
        "ai_payload": ai_payload,
        "semantic_payload": semantic_payload,
        "llm_payload": llm_payload,
    }


def build_stage4_selection_audit(outbox_dir: str | Path = "outbox") -> str:
    artifacts = _load_stage4_artifacts(outbox_dir)
    snapshot = dict(artifacts["snapshot_payload"].get("snapshot", {}))
    keyword_payload = artifacts["keyword_payload"]
    ai_payload = artifacts["ai_payload"]
    semantic_payload = artifacts["semantic_payload"]
    llm_payload = artifacts["llm_payload"]

    summary = dict(ai_payload.get("summary", {}))
    generated_at = summary.get("generated_at", "")
    keyword_summary = dict(summary.get("keyword", {}))
    semantic_summary = dict(summary.get("semantic", {}))
    llm_summary = dict(summary.get("llm", {}))
    ai_summary = dict(summary.get("ai", {}))

    final_items = _selection_payload_items(ai_payload)
    rule_rejections = _selection_payload_rejections(keyword_payload, "rule")
    semantic = dict(semantic_payload.get("semantic", semantic_summary))
    llm = dict(llm_payload.get("llm", llm_summary))
    semantic_rejections = [dict(item) for item in semantic.get("rejected_items", []) if isinstance(item, Mapping)]
    llm_rejections = [dict(item) for item in llm.get("rejected_items", []) if isinstance(item, Mapping)]

    source_counter = Counter(
        str(item.get("source_name") or item.get("source_id") or "").strip()
        for item in final_items
        if str(item.get("source_name") or item.get("source_id") or "").strip()
    )

    semantic_model = str(semantic.get("model") or semantic_summary.get("model") or "").strip()

    lines: list[str] = []
    lines.append("# Stage 4 Selection \u5ba1\u9605\u6587\u6863")
    lines.append("")
    lines.append(f"- \u751f\u6210\u65f6\u95f4: `{generated_at}`")
    lines.append(f"- \u8f93\u51fa\u76ee\u5f55: `{Path(outbox_dir)}`")
    lines.append("")

    lines.append("## \u672c\u6b21\u8fd0\u884c\u6982\u51b5")
    lines.append("")
    lines.append(f"- snapshot \u6a21\u5f0f: `{snapshot.get('mode', '')}`")
    lines.append(f"- snapshot \u603b\u6761\u76ee: {len(snapshot.get('items', []))}")
    lines.append(f"- snapshot \u65b0\u589e\u6761\u76ee: {len(snapshot.get('new_items', []))}")
    lines.append(f"- snapshot \u5931\u8d25\u6e90: {len(snapshot.get('failed_sources', []))}")
    lines.append(f"- standalone \u5206\u533a: {len(snapshot.get('standalone_sections', []))}")
    lines.append("")

    lines.append("## \u6f0f\u6597\u6982\u89c8")
    lines.append("")
    lines.append(f"- \u521d\u59cb\u5019\u9009\u6570: {int(keyword_summary.get('total_candidates', len(snapshot.get('items', []))) or 0)}")
    lines.append(f"- \u89c4\u5219\u5c42\u4fdd\u7559\u6570: {int(keyword_summary.get('qualified_count', 0) or 0)}")
    lines.append(f"- \u89c4\u5219\u5c42\u6dd8\u6c70\u6570: {len(rule_rejections)}")
    lines.append(f"- \u8bed\u4e49\u5c42\u4fdd\u7559\u6570: {int(semantic_summary.get('passed_count', 0) or 0)}")
    lines.append(f"- \u8bed\u4e49\u5c42\u6dd8\u6c70\u6570: {int(semantic_summary.get('rejected_count', 0) or 0)}")
    if semantic_model:
        lines.append(f"- \u8bed\u4e49 embedding \u6a21\u578b: `{semantic_model}`")
    lines.append(f"- LLM \u8bc4\u4f30\u6570: {int(llm_summary.get('evaluated_count', 0) or 0)}")
    lines.append(f"- LLM \u4fdd\u7559\u6570: {int(llm_summary.get('kept_count', 0) or 0)}")
    lines.append(f"- LLM \u6dd8\u6c70\u6570: {int(llm_summary.get('rejected_count', 0) or 0)}")
    lines.append(f"- \u6700\u7ec8\u4fdd\u7559\u6570: {int(ai_summary.get('qualified_count', len(final_items)) or len(final_items))}")
    lines.append("")

    lines.append("## \u6700\u7ec8\u6765\u6e90\u5206\u5e03")
    lines.append("")
    if source_counter:
        for source_name, count in source_counter.most_common(8):
            lines.append(f"- `{source_name}`: {count} \u6761")
    else:
        lines.append("- \u6700\u7ec8\u7ed3\u679c\u4e3a\u7a7a")
    lines.append("")

    _append_preview_section(
        lines,
        "\u89c4\u5219\u5c42\u6dd8\u6c70\u6837\u672c",
        rule_rejections,
        fallback="\u65e0\u89c4\u5219\u5c42\u6dd8\u6c70\u6837\u672c",
    )
    _append_preview_section(
        lines,
        "\u8bed\u4e49\u5c42\u6dd8\u6c70\u6837\u672c",
        semantic_rejections,
        fallback="\u65e0\u8bed\u4e49\u5c42\u6dd8\u6c70\u6837\u672c",
    )
    _append_preview_section(
        lines,
        "LLM \u5c42\u6dd8\u6c70\u6837\u672c",
        llm_rejections,
        fallback="\u65e0 LLM \u5c42\u6dd8\u6c70\u6837\u672c",
    )
    _append_preview_section(
        lines,
        "\u6700\u7ec8\u4fdd\u7559\u6837\u672c",
        final_items,
        fallback="\u65e0\u6700\u7ec8\u4fdd\u7559\u6837\u672c",
        rejected=False,
    )

    lines.append("## \u98ce\u9669\u63d0\u793a")
    lines.append("")
    risk_lines = _build_risk_lines(snapshot, semantic_summary, llm_summary, final_items, source_counter, ai_payload)
    if risk_lines:
        lines.extend(risk_lines)
    else:
        lines.append("- \u672a\u68c0\u6d4b\u5230\u663e\u8457\u98ce\u9669\u4fe1\u53f7")
    lines.append("")

    lines.append("## \u521d\u6b65\u5224\u65ad")
    lines.append("")
    lines.extend(_build_judgement_lines(keyword_summary, semantic_summary, llm_summary, final_items))
    lines.append("")

    return "\n".join(lines)


def write_stage4_selection_audit(
    *,
    outbox_dir: str | Path = "outbox",
    filename: str = "stage4_selection_audit.md",
) -> Path:
    outbox_path = Path(outbox_dir)
    outbox_path.mkdir(parents=True, exist_ok=True)
    output_path = outbox_path / filename
    output_path.write_text(
        build_stage4_selection_audit(outbox_dir),
        encoding=REVIEW_FILE_ENCODING,
    )
    return output_path


def _append_preview_section(
    lines: list[str],
    title: str,
    items: Sequence[Mapping[str, Any]],
    *,
    fallback: str,
    rejected: bool = True,
    max_items: int = 8,
) -> None:
    lines.append(f"## {title}")
    lines.append("")
    if not items:
        lines.append(f"- {fallback}")
        lines.append("")
        return

    for item in items[:max_items]:
        source_id = str(item.get("source_id", "")).strip()
        rank = item.get("current_rank", "")
        title_text = str(item.get("title", "")).strip()
        if rejected:
            lines.append(
                f"- [{source_id}] [{rank}] {title_text} -> {item.get('rejected_stage', '')}: {item.get('rejected_reason', '')}"
            )
        else:
            lines.append(f"- [{source_id}] [{rank}] {title_text}")
    if len(items) > max_items:
        lines.append(f"- ... \u5176\u4f59 {len(items) - max_items} \u6761\u5df2\u7701\u7565")
    lines.append("")


def _build_risk_lines(
    snapshot: Mapping[str, Any],
    semantic_summary: Mapping[str, Any],
    llm_summary: Mapping[str, Any],
    final_items: Sequence[Mapping[str, Any]],
    source_counter: Counter[str],
    ai_payload: Mapping[str, Any],
) -> list[str]:
    lines: list[str] = []

    failed_sources = snapshot.get("failed_sources", [])
    if isinstance(failed_sources, list) and failed_sources:
        source_ids = ", ".join(
            str(item.get("source_id", "")).strip()
            for item in failed_sources
            if isinstance(item, Mapping) and str(item.get("source_id", "")).strip()
        )
        if source_ids:
            lines.append(f"- \u5b58\u5728\u6293\u53d6\u5931\u8d25\u6e90: `{source_ids}`")

    if bool(semantic_summary.get("skipped")):
        reason = str(semantic_summary.get("reason", "") or "unknown").strip()
        lines.append(f"- \u8bed\u4e49\u5c42\u672a\u5b9e\u9645\u751f\u6548: {reason}")

    if bool(llm_summary.get("skipped")) or bool(ai_payload.get("skipped")):
        reason = str(ai_payload.get("reason", "") or llm_summary.get("reason", "") or "unknown").strip()
        lines.append(f"- LLM \u8d28\u91cf\u95f8\u95e8\u672a\u5b9e\u9645\u6267\u884c: {reason}")

    if not final_items:
        lines.append("- \u6700\u7ec8\u4fdd\u7559\u7ed3\u679c\u4e3a\u7a7a\uff0c\u9700\u8981\u68c0\u67e5\u89c4\u5219\u3001\u8bed\u4e49\u9608\u503c\u548c LLM \u8d28\u91cf\u9608\u503c\u662f\u5426\u8fc7\u4e25")

    if source_counter and final_items:
        top_source, top_count = source_counter.most_common(1)[0]
        share = top_count / max(len(final_items), 1)
        if share >= 0.6:
            lines.append(f"- \u6700\u7ec8\u7ed3\u679c\u5bf9 `{top_source}` \u4f9d\u8d56\u504f\u9ad8: {top_count}/{len(final_items)} ({share:.0%})")

    return lines


def _build_judgement_lines(
    keyword_summary: Mapping[str, Any],
    semantic_summary: Mapping[str, Any],
    llm_summary: Mapping[str, Any],
    final_items: Sequence[Mapping[str, Any]],
) -> list[str]:
    lines: list[str] = []
    initial_candidates = int(keyword_summary.get("total_candidates", 0) or 0)
    rule_kept = int(keyword_summary.get("qualified_count", 0) or 0)
    semantic_kept = int(semantic_summary.get("passed_count", 0) or 0)
    llm_kept = int(llm_summary.get("kept_count", 0) or 0)

    if initial_candidates > 0:
        lines.append(
            f"- \u5f53\u524d\u6f0f\u6597\u4ece {initial_candidates} \u6761\u5019\u9009\u9010\u6b65\u6536\u655b\u5230 {len(final_items)} \u6761\u6700\u7ec8\u65b0\u95fb\uff0c\u8bf4\u660e Selection \u4e3b\u94fe\u8def\u5df2\u6309\u201c\u89c4\u5219 -> \u8bed\u4e49 -> LLM\u201d\u7a33\u5b9a\u5de5\u4f5c\u3002"
        )
    if rule_kept and semantic_kept < rule_kept:
        lines.append(f"- \u8bed\u4e49\u5c42\u5df2\u627f\u62c5\u76f8\u5173\u6027\u8fc7\u6ee4\u804c\u8d23\uff1a{rule_kept} -> {semantic_kept}\u3002")
    if semantic_kept and llm_kept <= semantic_kept:
        lines.append(f"- LLM \u8d28\u91cf\u95f8\u95e8\u5df2\u627f\u62c5\u6700\u7ec8\u4fdd\u7559\u804c\u8d23\uff1a{semantic_kept} -> {llm_kept}\u3002")
    if final_items:
        lines.append("- \u7ed3\u8bba\uff1a\u5f53\u524d Selection \u5df2\u4ece\u201c\u4e3b\u9898\u5206\u7ec4\u5668\u201d\u6536\u53e3\u4e3a\u201c\u9ad8\u8d28\u91cf\u65b0\u95fb\u7b5b\u9009\u6f0f\u6597\u201d\uff0c\u53ef\u4ee5\u76f4\u63a5\u8854\u63a5\u540e\u7eed\u5206\u6790\u9636\u6bb5\u3002")
    else:
        lines.append("- \u7ed3\u8bba\uff1a\u5f53\u524d\u6f0f\u6597\u7ed3\u6784\u5df2\u5c31\u4f4d\uff0c\u4f46\u9608\u503c\u6216\u5174\u8da3\u9762\u4ecd\u9700\u7ee7\u7eed\u6821\u51c6\uff0c\u624d\u80fd\u7a33\u5b9a\u4ea7\u51fa\u8db3\u591f\u6570\u91cf\u7684\u9ad8\u8d28\u91cf\u65b0\u95fb\u3002")
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the stage-4 selection audit markdown from outbox artifacts.",
    )
    parser.add_argument("--outbox", default="outbox")
    parser.add_argument("--filename", default="stage4_selection_audit.md")
    args = parser.parse_args(list(argv) if argv is not None else None)

    output_path = write_stage4_selection_audit(
        outbox_dir=args.outbox,
        filename=args.filename,
    )
    print(str(output_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
