from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Optional

from pipeline.errors import PipelineStepError
from pipeline.language import detect_language, languages_match
from pipeline.nodes.runner import record_step
from pipeline.state import PipelineState, model_dump_safe
from pipeline.validation import persist_if_repaired, validate_quiz_file


def _collect_quiz_text(node) -> str:
    parts = []
    if isinstance(node, dict):
        if isinstance(node.get("title"), str):
            parts.append(node["title"])
        if isinstance(node.get("summary"), str):
            parts.append(node["summary"])
        if isinstance(node.get("questions"), list):
            for q in node["questions"]:
                if isinstance(q, dict):
                    parts.append(str(q.get("question", "")))
                    parts.extend([str(o) for o in (q.get("options") or [])])
                    parts.append(str(q.get("correct_answer") or q.get("answer") or ""))
        for key, value in node.items():
            if key != "questions":
                parts.append(_collect_quiz_text(value))
    elif isinstance(node, list):
        for item in node:
            parts.append(_collect_quiz_text(item))
    return " ".join([p for p in parts if p])


def validate_quiz(state: PipelineState, log_fn: Optional[Callable[[str], None]] = None) -> dict:
    start = time.time()
    state.quiz_validation_attempts += 1
    state.quiz_regen_required = False
    path = Path(state.paths.get("quiz_json", ""))
    result = validate_quiz_file(path)

    if not result.valid:
        state.quiz_validation_failed = True
        state.quiz_regen_required = False
        error = "; ".join(result.errors) or "Quiz validation failed"
        state.last_error = error
        if log_fn:
            log_fn(f"Validate quiz failed: {error}")
        record_step(
            state,
            step_name="Validate quiz",
            duration_seconds=round(time.time() - start, 2),
            status="failed",
            error=error,
        )
        if state.quiz_validation_attempts >= state.quiz_validation_max:
            raise PipelineStepError(f"Validate quiz failed: {error}", state)
        return model_dump_safe(state)

    persist_if_repaired(path, result)
    data = result.data or {}

    language_error = None
    if state.language:
        lang_text = _collect_quiz_text(data)
        lang, _conf = detect_language(lang_text)
        if lang and not languages_match(state.language, lang):
            language_error = f"Quiz language '{lang}' does not match '{state.language}'"

    if language_error:
        state.quiz_validation_failed = True
        state.quiz_regen_required = True
        state.last_error = language_error
        if log_fn:
            log_fn(f"Validate quiz failed: {language_error}")
        record_step(
            state,
            step_name="Validate quiz",
            duration_seconds=round(time.time() - start, 2),
            status="failed",
            error=language_error,
        )
        if state.quiz_validation_attempts >= state.quiz_validation_max:
            raise PipelineStepError(f"Validate quiz failed: {language_error}", state)
        return model_dump_safe(state)

    state.quiz_validation_failed = False
    if log_fn:
        log_fn("Validate quiz: OK")
    record_step(
        state,
        step_name="Validate quiz",
        duration_seconds=round(time.time() - start, 2),
        status="success",
    )
    return model_dump_safe(state)
