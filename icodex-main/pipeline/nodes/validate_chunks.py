from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Optional

from pipeline.errors import PipelineStepError
from pipeline.nodes.runner import record_step
from pipeline.state import PipelineState, model_dump_safe
from pipeline.validation import persist_if_repaired, validate_chunks_file


def validate_chunks(state: PipelineState, log_fn: Optional[Callable[[str], None]] = None) -> dict:
    start = time.time()
    state.chunk_validation_attempts += 1
    path = Path(state.paths.get("chunks", ""))
    result = validate_chunks_file(path)

    if result.valid:
        state.chunk_validation_failed = False
        persist_if_repaired(path, result)
        if log_fn:
            log_fn("Validate chunks: OK")
        record_step(
            state,
            step_name="Validate chunks",
            duration_seconds=round(time.time() - start, 2),
            status="success",
        )
        return model_dump_safe(state)

    state.chunk_validation_failed = True
    error = "; ".join(result.errors) or "Chunk validation failed"
    state.last_error = error
    if log_fn:
        log_fn(f"Validate chunks failed: {error}")
    record_step(
        state,
        step_name="Validate chunks",
        duration_seconds=round(time.time() - start, 2),
        status="failed",
        error=error,
    )
    if state.chunk_validation_attempts >= state.chunk_validation_max:
        raise PipelineStepError(f"Validate chunks failed: {error}", state)

    return model_dump_safe(state)
