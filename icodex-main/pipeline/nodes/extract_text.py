from __future__ import annotations

from typing import Callable, Optional

from pipeline.config import PYTHON_EXE, SCRIPT_PATHS
from pipeline.nodes.runner import run_subprocess_step
from pipeline.state import PipelineState, model_dump_safe


def extract_text(state: PipelineState, log_fn: Optional[Callable[[str], None]] = None) -> dict:
    cmd = [
        PYTHON_EXE,
        str(SCRIPT_PATHS["files_to_text"]),
        "--source-dir",
        state.job_dir,
        "--output",
        state.paths["raw_text"],
        "--files",
        *state.source_files,
    ]
    run_subprocess_step(state, step_name="Extract text", cmd=cmd, log_fn=log_fn)
    return model_dump_safe(state)
