from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from pipeline.errors import PipelineStepError
from pipeline.legacy import load_structure_module
from pipeline.nodes.runner import record_step
from pipeline.state import PipelineState, model_dump_safe


def _item_key_tuple(item: Dict[str, str]) -> tuple[str, str, str]:
    return (item.get("path", ""), item.get("title", ""), item.get("summary", ""))


def _merge_seed_items(legacy, structure: Dict[str, Any]) -> List[Dict[str, Any]]:
    seed_items = legacy._iter_mini_concept_items(structure)
    if seed_items:
        return seed_items
    return legacy._iter_summary_items(structure)


def _build_llm_inputs(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    inputs: List[Dict[str, Any]] = []
    for idx, item in enumerate(items):
        mc = item.get("mini_concept") or {}
        evidence = mc.get("source_evidence") or mc.get("sourceEvidence") or []
        if not isinstance(evidence, list):
            evidence = [str(evidence)]
        keywords = mc.get("keywords") or []
        if not isinstance(keywords, list):
            keywords = [str(keywords)]
        inputs.append(
            {
                "index": idx,
                "path": item.get("path", ""),
                "title": str(mc.get("title", "")).strip(),
                "summary": str(mc.get("summary", "")).strip(),
                "keywords": [str(k).strip() for k in keywords[:8] if str(k).strip()],
                "evidence": [str(e).strip() for e in evidence[:3] if str(e).strip()],
            }
        )
    return inputs


def regenerate_questions(state: PipelineState, log_fn: Optional[Callable[[str], None]] = None) -> dict:
    start = time.time()
    missing_items = state.question_missing_items or []
    if not missing_items:
        record_step(
            state,
            step_name="Regenerate questions",
            duration_seconds=round(time.time() - start, 2),
            status="success",
        )
        return model_dump_safe(state)

    quiz_path = Path(state.paths.get("quiz_json", ""))
    if not quiz_path.exists():
        raise PipelineStepError("Quiz JSON not found for regeneration.", state)

    structure = json.loads(quiz_path.read_text(encoding="utf-8"))
    legacy = load_structure_module()

    seed_items = _merge_seed_items(legacy, structure)
    limit = min(state.question_target or 0, len(seed_items))
    if limit <= 0:
        raise PipelineStepError("No mini-concepts available for regeneration.", state)
    selected_items = legacy._select_balanced_technical(seed_items, limit)
    item_map: Dict[tuple[str, str, str], Dict[str, Any]] = {}
    for item in selected_items:
        mc = item.get("mini_concept") or {}
        key = (
            str(item.get("path", "")).strip(),
            str(mc.get("title", "")).strip(),
            str(mc.get("summary", "")).strip(),
        )
        item_map[key] = item

    regen_items: List[Dict[str, Any]] = []
    for raw_key in missing_items:
        key_tuple = _item_key_tuple(raw_key)
        item = item_map.get(key_tuple)
        if item:
            regen_items.append(item)

    if not regen_items:
        raise PipelineStepError("No matching mini-concepts found for regeneration.", state)

    batch_size = 20
    generated = 0
    for i in range(0, len(regen_items), batch_size):
        batch = regen_items[i : i + batch_size]
        llm_inputs = _build_llm_inputs(batch)
        output = legacy.generate_questions_batch(llm_inputs, state.api_key, state.model, timeout=300)
        if not output:
            continue
        by_index: Dict[int, Dict[str, Any]] = {}
        for q in output:
            if not isinstance(q, dict):
                continue
            try:
                idx = int(q.get("index"))
            except Exception:
                continue
            by_index[idx] = q
        for idx, item in enumerate(batch):
            q = by_index.get(idx)
            if not q:
                continue
            cleaned = legacy.ensure_options(
                [
                    {
                        "question": q.get("question", ""),
                        "options": q.get("options", []),
                        "correct_answer": q.get("correct_answer", ""),
                    }
                ]
            )
            if not cleaned:
                continue
            if not str(cleaned[0].get("id") or "").strip():
                cleaned[0]["id"] = uuid.uuid4().hex
            concept_ref = item.get("concept_ref")
            if isinstance(concept_ref, dict):
                concept_ref.setdefault("questions", []).append(cleaned[0])
                generated += 1

    quiz_path.write_text(json.dumps(structure, ensure_ascii=False, indent=2), encoding="utf-8")
    remaining = max(0, len(regen_items) - generated)
    state.questions_missing = remaining
    state.question_review_failed = remaining > 0
    if remaining == 0:
        state.question_missing_items = []

    if log_fn:
        log_fn(f"Regenerated {generated}/{len(regen_items)} questions.")

    record_step(
        state,
        step_name="Regenerate questions",
        duration_seconds=round(time.time() - start, 2),
        status="success" if generated > 0 else "failed",
        error=None if generated > 0 else "Regeneration produced no questions",
    )
    if generated == 0:
        raise PipelineStepError("Regeneration produced no questions.", state)
    return model_dump_safe(state)
