from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from pipeline.cache import cache_enabled, cache_path, hash_bytes, read_cached, write_cached
from pipeline.config import DEFAULT_MAX_MINI_CONCEPTS, PYTHON_EXE, SCRIPT_PATHS
from pipeline.config import PROMPT_VERSIONS
from pipeline.nodes.runner import run_subprocess_step
from pipeline.nodes.runner import record_step
from pipeline.state import PipelineState, model_dump_safe


def structure_text(state: PipelineState, log_fn: Optional[Callable[[str], None]] = None) -> dict:
    if cache_enabled(state.env) and state.structure_validation_attempts == 0:
        input_path = Path(state.paths["chunks"])
        if input_path.exists():
            input_bytes = input_path.read_bytes()
            key = hash_bytes(
                state.model.encode(),
                PROMPT_VERSIONS["structure_text"].encode(),
                input_bytes,
                str(state.raw_bank_questions).encode(),
                str(DEFAULT_MAX_MINI_CONCEPTS).encode(),
            )
            cached_path = cache_path(state.job_dir, "structure_text", key, ".json")
            cached = read_cached(cached_path)
            if cached is not None:
                Path(state.paths["structure"]).write_bytes(cached)
                record_step(state, step_name="Build structure", duration_seconds=0.0, status="success")
                if log_fn:
                    log_fn("Build structure: cache hit")
                return model_dump_safe(state)

    cmd = [
        PYTHON_EXE,
        str(SCRIPT_PATHS["chunks_to_structure"]),
        "-i",
        state.paths["chunks"],
        "-o",
        state.paths["structure"],
        "--target-mini-concepts",
        str(state.raw_bank_questions),
        "--max-mini-concepts",
        str(DEFAULT_MAX_MINI_CONCEPTS),
        "-m",
        state.model,
    ]
    run_subprocess_step(state, step_name="Build structure", cmd=cmd, log_fn=log_fn)
    if cache_enabled(state.env):
        structure_path = Path(state.paths["structure"])
        input_path = Path(state.paths["chunks"])
        if structure_path.exists() and input_path.exists():
            input_bytes = input_path.read_bytes()
            key = hash_bytes(
                state.model.encode(),
                PROMPT_VERSIONS["structure_text"].encode(),
                input_bytes,
                str(state.raw_bank_questions).encode(),
                str(DEFAULT_MAX_MINI_CONCEPTS).encode(),
            )
            cached_path = cache_path(state.job_dir, "structure_text", key, ".json")
            write_cached(cached_path, structure_path.read_bytes())
    return model_dump_safe(state)
