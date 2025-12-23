from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable, Optional

from pipeline.nodes.runner import record_step
from pipeline.repair import repair_json_with_llm
from pipeline.schemas import CourseWrapper
from pipeline.state import PipelineState, model_dump_safe


def _schema_hint() -> str:
    if hasattr(CourseWrapper, "model_json_schema"):
        return json.dumps(CourseWrapper.model_json_schema(by_alias=False), ensure_ascii=False)
    return json.dumps(CourseWrapper.schema(), ensure_ascii=False)  # type: ignore[attr-defined]


def repair_quiz(state: PipelineState, log_fn: Optional[Callable[[str], None]] = None) -> dict:
    start = time.time()
    state.quiz_repair_attempts += 1
    path = Path(state.paths.get("quiz_json", ""))
    raw_text = ""
    if path.exists():
        raw_text = path.read_text(encoding="utf-8", errors="ignore")
    fixed = None
    if state.api_key and raw_text.strip():
        fixed = repair_json_with_llm(
            raw_text,
            schema_hint=_schema_hint(),
            api_key=state.api_key,
            model=state.model,
        )
    if fixed:
        path.write_text(fixed, encoding="utf-8")
        if log_fn:
            log_fn("Repaired quiz JSON with LLM.")
    else:
        if log_fn:
            log_fn("Quiz repair attempt did not produce a fix.")

    record_step(
        state,
        step_name="Repair quiz",
        duration_seconds=round(time.time() - start, 2),
        status="success" if fixed else "failed",
        error=None if fixed else "Repair failed",
    )
    return model_dump_safe(state)
