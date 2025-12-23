from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from pipeline.errors import PipelineStepError
from pipeline.legacy import load_reviewer_module, load_structure_module
from pipeline.nodes.runner import record_step
from pipeline.state import PipelineState, model_dump_safe


_TOKEN_RE = re.compile(r"\w+", re.UNICODE)
_VAGUE_PREFIXES = (
    "what is",
    "which is",
    "choose the correct",
    "select the correct",
)


def _tokenize(text: str) -> Set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text or "") if t.strip()}


def _item_key(item: Dict[str, Any]) -> Dict[str, str]:
    mc = item.get("mini_concept") or {}
    return {
        "path": str(item.get("path", "")).strip(),
        "title": str(mc.get("title", "")).strip(),
        "summary": str(mc.get("summary", "")).strip(),
    }


def _item_key_tuple(key: Dict[str, str]) -> tuple[str, str, str]:
    return (key.get("path", ""), key.get("title", ""), key.get("summary", ""))


def _merge_seed_items(structure: Dict[str, Any]) -> List[Dict[str, Any]]:
    legacy = load_structure_module()
    seed_items = legacy._iter_mini_concept_items(structure)
    if seed_items:
        return seed_items
    return legacy._iter_summary_items(structure)


def _select_items(structure: Dict[str, Any], target: int) -> List[Dict[str, Any]]:
    legacy = load_structure_module()
    items = _merge_seed_items(structure)
    limit = min(max(0, int(target or 0)), len(items))
    if limit <= 0:
        return []
    return legacy._select_balanced_technical(items, limit)


def _flatten_with_items(structure: Dict[str, Any], selected_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items_by_concept: Dict[int, List[Dict[str, Any]]] = {}
    for item in selected_items:
        concept_ref = item.get("concept_ref")
        if not isinstance(concept_ref, dict):
            continue
        items_by_concept.setdefault(id(concept_ref), []).append(item)

    flat: List[Dict[str, Any]] = []

    def walk(node: Any, trail: List[str]) -> None:
        if isinstance(node, dict):
            title = node.get("title") or node.get("name")
            title_str = str(title).strip() if title else ""
            next_trail = trail + [title_str] if title_str else trail
            questions = node.get("questions")
            if isinstance(questions, list):
                concept_items = items_by_concept.get(id(node), [])
                for idx, question in enumerate(questions):
                    item = concept_items[idx] if idx < len(concept_items) else None
                    flat.append(
                        {
                            "question": question,
                            "node": node,
                            "path": " / ".join([t for t in next_trail if t]),
                            "item": item,
                        }
                    )
            for key, value in node.items():
                if key == "questions":
                    continue
                walk(value, next_trail)
        elif isinstance(node, list):
            for item in node:
                walk(item, trail)

    walk(structure, [])
    return flat


def _normalize_signature(question: Dict[str, Any]) -> str:
    text = str(question.get("question", ""))[:400].strip().lower()
    options = question.get("options") or []
    opts_norm = " | ".join(sorted([str(o).strip().lower() for o in options if str(o).strip()]))
    return f"{text} || {opts_norm}"


def _is_vague(question_text: str) -> bool:
    q = (question_text or "").strip().lower()
    if len(q.split()) < 5:
        return True
    for prefix in _VAGUE_PREFIXES:
        if q.startswith(prefix):
            return True
    return False


def _is_grounded(question: Dict[str, Any], item: Optional[Dict[str, Any]]) -> bool:
    if not item:
        return False
    mc = item.get("mini_concept") or {}
    keywords = mc.get("keywords") or []
    evidence = mc.get("source_evidence") or mc.get("sourceEvidence") or []
    if not isinstance(keywords, list):
        keywords = [str(keywords)]
    if not isinstance(evidence, list):
        evidence = [str(evidence)]
    text = " ".join(
        [
            str(question.get("question", "")),
            str(question.get("correct_answer") or question.get("answer") or ""),
        ]
    )
    text_tokens = _tokenize(text)
    keyword_tokens = _tokenize(" ".join([str(k) for k in keywords]))
    evidence_tokens = _tokenize(" ".join([str(e) for e in evidence]))
    if not keyword_tokens and not evidence_tokens:
        return True
    if keyword_tokens and text_tokens.intersection(keyword_tokens):
        return True
    if evidence_tokens and text_tokens.intersection(evidence_tokens):
        return True
    return False


def review_questions(state: PipelineState, log_fn: Optional[Callable[[str], None]] = None) -> dict:
    start = time.time()
    state.question_review_attempts += 1
    state.question_missing_items = []
    state.questions_missing = 0
    state.review_notes = None

    path = Path(state.paths.get("quiz_json", ""))
    if not path.exists():
        state.question_review_failed = True
        state.last_error = "Quiz JSON not found for review."
        record_step(
            state,
            step_name="Review questions",
            duration_seconds=round(time.time() - start, 2),
            status="failed",
            error=state.last_error,
        )
        raise PipelineStepError(state.last_error, state)

    try:
        structure = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise PipelineStepError(f"Unable to read quiz JSON: {exc}", state)
    target = state.question_target or 0
    selected_items = _select_items(structure, target)
    if target and not selected_items:
        raise PipelineStepError("No selectable mini-concepts for review.", state)
    flat = _flatten_with_items(structure, selected_items)

    flat_payload = [{"question": f["question"], "path": f["path"]} for f in flat]
    reviewer = load_reviewer_module()
    review_result = reviewer.review_questions(flat_payload, state.api_key, state.model, timeout=300)
    invalid_raw = review_result.get("invalid_indices") or []
    if not isinstance(invalid_raw, list):
        invalid_raw = []
    invalid_indices = set(invalid_raw)
    notes = review_result.get("notes", "OK")

    # Additional validation: duplicates, vagueness, grounding, options.
    seen_sigs: Dict[str, int] = {}
    for idx, entry in enumerate(flat):
        question = entry.get("question") or {}
        if not isinstance(question, dict):
            invalid_indices.add(idx)
            continue
        sig = _normalize_signature(question)
        if sig and sig in seen_sigs:
            invalid_indices.add(idx)
        else:
            seen_sigs[sig] = idx

        options = question.get("options") or []
        if not isinstance(options, list) or len(options) != 4:
            invalid_indices.add(idx)
        if len(set([str(o) for o in options])) != len(options):
            invalid_indices.add(idx)
        correct = question.get("correct_answer") or question.get("answer") or ""
        if correct not in options:
            invalid_indices.add(idx)

        q_text = str(question.get("question", ""))
        if _is_vague(q_text):
            invalid_indices.add(idx)

        if not _is_grounded(question, entry.get("item")):
            invalid_indices.add(idx)

        for opt in options:
            opt_text = str(opt).strip().lower()
            if opt_text.startswith("choice ") or opt_text.startswith("option "):
                invalid_indices.add(idx)

    invalid_indices = sorted(invalid_indices)
    state.review_notes = notes if notes else "OK"

    # Remove invalid questions from structure.
    if invalid_indices:
        legacy = load_structure_module()
        simple_flat = [{"question": f["question"], "node": f["node"]} for f in flat]
        legacy.remove_invalid_questions_from_flat(simple_flat, invalid_indices)

    # Determine missing items after removal.
    remaining_keys = set()
    for idx, entry in enumerate(flat):
        if idx in invalid_indices:
            continue
        item = entry.get("item")
        if isinstance(item, dict):
            remaining_keys.add(_item_key_tuple(_item_key(item)))

    missing_keys: List[Dict[str, str]] = []
    for item in selected_items:
        key = _item_key(item)
        if _item_key_tuple(key) not in remaining_keys:
            missing_keys.append(key)

    state.question_missing_items = missing_keys
    current_count = len(flat) - len(invalid_indices)
    state.questions_missing = max(0, int(target or 0) - current_count)
    state.question_review_failed = bool(invalid_indices or state.questions_missing)

    # Persist updated quiz after removals.
    path.write_text(json.dumps(structure, ensure_ascii=False, indent=2), encoding="utf-8")

    if state.question_review_failed:
        error = (
            f"Reviewer flagged {len(invalid_indices)} question(s); "
            f"missing {state.questions_missing}/{target}."
        )
        state.last_error = error
        if log_fn:
            log_fn(error)
        record_step(
            state,
            step_name="Review questions",
            duration_seconds=round(time.time() - start, 2),
            status="failed",
            error=error,
        )
        if state.question_review_attempts >= state.question_review_max:
            raise PipelineStepError(error, state)
    else:
        evidence_path_str = state.paths.get("evidence_json")
        if evidence_path_str:
            try:
                evidence_payload = {
                    "version": 1,
                    "questions": [],
                }
                for entry in flat:
                    question = entry.get("question") or {}
                    if not isinstance(question, dict):
                        continue
                    qid = str(question.get("id") or "").strip()
                    if not qid:
                        qid = str(question.get("question") or "").strip()
                    item = entry.get("item") or {}
                    mc = (item.get("mini_concept") or {}) if isinstance(item, dict) else {}
                    evidence = mc.get("source_evidence") or mc.get("sourceEvidence") or []
                    if not isinstance(evidence, list):
                        evidence = [evidence]
                    evidence_payload["questions"].append(
                        {
                            "id": qid or None,
                            "question": str(question.get("question") or "").strip(),
                            "position": str(entry.get("path") or "").strip(),
                            "mini_concept_title": str(mc.get("title") or "").strip(),
                            "evidence": [str(e).strip() for e in evidence if str(e).strip()],
                        }
                    )

                Path(evidence_path_str).write_text(
                    json.dumps(evidence_payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                if log_fn:
                    log_fn(f"Wrote evidence sidecar: {evidence_path_str}")
            except Exception as exc:  # noqa: BLE001
                if log_fn:
                    log_fn(f"Warning: failed to write evidence sidecar: {exc}")

        if log_fn:
            log_fn("Reviewer approved all questions.")
        record_step(
            state,
            step_name="Review questions",
            duration_seconds=round(time.time() - start, 2),
            status="success",
        )

    return model_dump_safe(state)
