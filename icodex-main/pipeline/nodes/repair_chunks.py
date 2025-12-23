from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Optional

from pipeline.nodes.runner import record_step
from pipeline.state import PipelineState, model_dump_safe
from pipeline.validation import persist_if_repaired, validate_chunks_file


def repair_chunks(state: PipelineState, log_fn: Optional[Callable[[str], None]] = None) -> dict:
    start = time.time()
    state.chunk_repair_attempts += 1
    path = Path(state.paths.get("chunks", ""))
    result = validate_chunks_file(path)
    persist_if_repaired(path, result)

    if log_fn:
        if result.repaired:
            log_fn("Repaired chunks JSON format.")
        else:
            log_fn("Chunks repair attempt completed.")
    record_step(
        state,
        step_name="Repair chunks",
        duration_seconds=round(time.time() - start, 2),
        status="success",
    )
    return model_dump_safe(state)
