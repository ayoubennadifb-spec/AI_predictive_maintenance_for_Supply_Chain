from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from pipeline.schemas import ChunkOutput, CourseWrapper, EvidenceSidecar, Question


@dataclass
class ValidationResult:
    valid: bool
    errors: List[str]
    data: Optional[Dict[str, Any]] = None
    repaired: bool = False


def _model_validate(model, data):
    if hasattr(model, "model_validate"):
        return model.model_validate(data)
    return model.parse_obj(data)  # type: ignore[call-arg]


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _ensure_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def normalize_chunks(data: Dict[str, Any]) -> Dict[str, Any]:
    chunks = _ensure_list(data.get("chunks"))
    normalized: List[Dict[str, Any]] = []
    for idx, item in enumerate(chunks, start=1):
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", ""))
        char_count = item.get("char_count")
        word_count = item.get("word_count")
        if char_count is None:
            char_count = len(text)
        if word_count is None:
            word_count = len(text.split())
        normalized.append(
            {
                "id": int(item.get("id") or idx),
                "text": text,
                "char_count": int(char_count),
                "word_count": int(word_count),
            }
        )
    return {"total_chunks": len(normalized), "chunks": normalized}


def normalize_structure(data: Dict[str, Any]) -> Dict[str, Any]:
    if "course" not in data and isinstance(data, dict):
        if "modules" in data:
            data = {"course": data}

    def norm_node(node: Any) -> Any:
        if isinstance(node, list):
            return [norm_node(item) for item in node if item is not None]
        if not isinstance(node, dict):
            return node

        if "title" not in node and "name" in node:
            node["title"] = node.get("name")
        if "name" in node:
            node.pop("name", None)
        if "sourceEvidence" in node:
            node["source_evidence"] = node.get("sourceEvidence")
            node.pop("sourceEvidence", None)
        if "miniConcepts" in node:
            node["mini_concepts"] = node.get("miniConcepts")
            node.pop("miniConcepts", None)
        if "miniModules" in node:
            node["mini_modules"] = node.get("miniModules")
            node.pop("miniModules", None)

        for key in ("keywords", "source_evidence", "mini_concepts", "mini_modules", "modules", "concepts"):
            if key in node:
                node[key] = _ensure_list(node[key])

        for key in ("description", "summary", "title"):
            if key in node and node[key] is None:
                node[key] = ""

        for key, value in list(node.items()):
            node[key] = norm_node(value)
        return node

    return norm_node(data)


def normalize_quiz(data: Dict[str, Any]) -> Dict[str, Any]:
    def norm_node(node: Any) -> Any:
        if isinstance(node, list):
            return [norm_node(item) for item in node if item is not None]
        if not isinstance(node, dict):
            return node
        if "questions" in node:
            questions = _ensure_list(node.get("questions"))
            normalized_questions = []
            for q in questions:
                if not isinstance(q, dict):
                    continue
                if "correctAnswer" in q and "correct_answer" not in q:
                    q["correct_answer"] = q.get("correctAnswer")
                    q.pop("correctAnswer", None)
                if "correct_answer" not in q and "answer" in q:
                    q["correct_answer"] = q.get("answer")
                if "answer" in q:
                    q.pop("answer", None)
                if "options" in q and not isinstance(q.get("options"), list):
                    q["options"] = _ensure_list(q.get("options"))
                normalized_questions.append(q)
            node["questions"] = normalized_questions
        for key, value in list(node.items()):
            node[key] = norm_node(value)
        return node

    return norm_node(data)


def _dedupe_preserve(values: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _repair_question_options(options: List[str], correct: str) -> List[str]:
    options = [str(o).strip() for o in (options or []) if str(o).strip()]
    correct = str(correct or "").strip()

    unique = _dedupe_preserve(options)
    if correct and correct not in unique:
        unique.insert(0, correct)

    filler_idx = 1
    while len(unique) < 4:
        filler = f"Choice {filler_idx}"
        filler_idx += 1
        if filler == correct or filler in unique:
            continue
        unique.append(filler)

    if len(unique) > 4:
        if correct and correct in unique[:4]:
            unique = unique[:4]
        elif correct and correct in unique:
            trimmed = unique[:3]
            if correct not in trimmed:
                trimmed.append(correct)
            unique = trimmed
        else:
            unique = unique[:4]

    return unique


def validate_chunks_file(path: Path) -> ValidationResult:
    try:
        raw = _read_json(path)
    except Exception as exc:
        return ValidationResult(False, [f"Invalid JSON: {exc}"])

    normalized = normalize_chunks(raw)
    try:
        _model_validate(ChunkOutput, normalized)
    except ValidationError as exc:
        return ValidationResult(False, [str(exc)], data=normalized, repaired=True)
    return ValidationResult(True, [], data=normalized, repaired=normalized != raw)


def validate_structure_file(path: Path) -> ValidationResult:
    try:
        raw = _read_json(path)
    except Exception as exc:
        return ValidationResult(False, [f"Invalid JSON: {exc}"])

    normalized = normalize_structure(raw)
    try:
        _model_validate(CourseWrapper, normalized)
    except ValidationError as exc:
        return ValidationResult(False, [str(exc)], data=normalized, repaired=True)
    return ValidationResult(True, [], data=normalized, repaired=normalized != raw)


def validate_quiz_file(path: Path) -> ValidationResult:
    try:
        raw = _read_json(path)
    except Exception as exc:
        return ValidationResult(False, [f"Invalid JSON: {exc}"])

    normalized = normalize_quiz(raw)
    try:
        _model_validate(CourseWrapper, normalized)
    except ValidationError as exc:
        return ValidationResult(False, [str(exc)], data=normalized, repaired=True)

    # Validate + deterministically repair question-level rules.
    errors: List[str] = []
    questions: List[Dict[str, Any]] = []
    repaired_any = False

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            qs = node.get("questions")
            if isinstance(qs, list):
                questions.extend(qs)
            for key, value in node.items():
                if key != "questions":
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(normalized)

    for idx, q in enumerate(questions):
        try:
            model = _model_validate(Question, q)
        except ValidationError as exc:
            errors.append(f"Question[{idx}] schema invalid: {exc}")
            continue

        # Repair options deterministically (no LLM): dedupe, ensure correct included, pad to 4.
        raw_options = [str(o) for o in (q.get("options") or [])]
        correct = str(q.get("correct_answer") or "").strip()
        if correct != str(q.get("correct_answer") or ""):
            q["correct_answer"] = correct
            repaired_any = True
        fixed_options = _repair_question_options(raw_options, correct)
        if fixed_options != raw_options:
            q["options"] = fixed_options
            repaired_any = True

        options = [str(o) for o in (q.get("options") or [])]
        if len(options) != 4:
            errors.append(f"Question[{idx}] has {len(options)} options; expected 4")
        if len(set(options)) != len(options):
            errors.append(f"Question[{idx}] has duplicate options")
        if correct not in options:
            errors.append(f"Question[{idx}] correct_answer not in options")

    if errors:
        return ValidationResult(False, errors, data=normalized, repaired=normalized != raw or repaired_any)

    return ValidationResult(True, [], data=normalized, repaired=normalized != raw or repaired_any)


def validate_evidence_file(path: Path) -> ValidationResult:
    try:
        raw = _read_json(path)
    except Exception as exc:
        return ValidationResult(False, [f"Invalid JSON: {exc}"])

    try:
        _model_validate(EvidenceSidecar, raw)
    except ValidationError as exc:
        return ValidationResult(False, [str(exc)], data=raw, repaired=False)

    return ValidationResult(True, [], data=raw, repaired=False)


def persist_if_repaired(path: Path, result: ValidationResult) -> None:
    if result.repaired and result.data is not None:
        _write_json(path, result.data)
