from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Optional

from pipeline.language import detect_language
from pipeline.nodes.runner import record_step
from pipeline.state import PipelineState, model_dump_safe


def detect_language_node(state: PipelineState, log_fn: Optional[Callable[[str], None]] = None) -> dict:
    start = time.time()
    lang = None
    confidence = None
    try:
        for key in ("cleaned_text", "raw_text"):
            candidate = Path(state.paths.get(key, ""))
            if candidate.exists():
                text = candidate.read_text(encoding="utf-8", errors="ignore")
                lang, confidence = detect_language(text)
                break
    except Exception:
        lang = None
        confidence = None

    state.language = lang
    state.language_confidence = confidence
    if log_fn:
        if lang:
            log_fn(f"Detected language: {lang}")
        else:
            log_fn("Detected language: unknown")
    record_step(
        state,
        step_name="Detect language",
        duration_seconds=round(time.time() - start, 2),
        status="success",
    )
    return model_dump_safe(state)
