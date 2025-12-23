from __future__ import annotations

from typing import Callable, Optional

from pipeline.config import PYTHON_EXE, SCRIPT_PATHS
from pipeline.nodes.runner import run_subprocess_step
from pipeline.state import PipelineState, model_dump_safe


def annotate_difficulty(state: PipelineState, log_fn: Optional[Callable[[str], None]] = None) -> dict:
    cmd = [
        PYTHON_EXE,
        str(SCRIPT_PATHS["difficulty_assessor"]),
        "-i",
        state.paths["quiz_json"],
        "--in-place",
        "-m",
        state.model,
    ]
    run_subprocess_step(state, step_name="Annotate difficulty", cmd=cmd, log_fn=log_fn)
    return model_dump_safe(state)
