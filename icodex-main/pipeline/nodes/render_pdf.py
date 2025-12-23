from __future__ import annotations

from typing import Callable, Optional

from pipeline.config import PYTHON_EXE, SCRIPT_PATHS
from pipeline.nodes.runner import run_subprocess_step
from pipeline.state import PipelineState, model_dump_safe


def render_pdf(state: PipelineState, log_fn: Optional[Callable[[str], None]] = None) -> dict:
    cmd = [
        PYTHON_EXE,
        str(SCRIPT_PATHS["quiz_to_pdf"]),
        "-i",
        state.paths["quiz_json"],
        "-o",
        state.paths["quiz_pdf"],
        "--limit",
        str(state.display_limit),
    ]
    run_subprocess_step(state, step_name="Render PDF", cmd=cmd, log_fn=log_fn)
    return model_dump_safe(state)
