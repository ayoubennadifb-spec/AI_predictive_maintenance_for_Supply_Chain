from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from pipeline.cache import cache_enabled, cache_path, hash_bytes, read_cached, write_cached
from pipeline.config import PROMPT_VERSIONS
from pipeline.config import PYTHON_EXE, SCRIPT_PATHS
from pipeline.nodes.runner import run_subprocess_step
from pipeline.nodes.runner import record_step
from pipeline.state import PipelineState, model_dump_safe


def chunk_text(state: PipelineState, log_fn: Optional[Callable[[str], None]] = None) -> dict:
    if cache_enabled(state.env) and state.chunk_validation_attempts == 0:
        input_path = Path(state.paths["text"])
        if input_path.exists():
            input_bytes = input_path.read_bytes()
            key = hash_bytes(state.model.encode(), PROMPT_VERSIONS["chunk_text"].encode(), input_bytes)
            cached_path = cache_path(state.job_dir, "chunk_text", key, ".json")
            cached = read_cached(cached_path)
            if cached is not None:
                Path(state.paths["chunks"]).write_bytes(cached)
                record_step(state, step_name="Chunk text", duration_seconds=0.0, status="success")
                if log_fn:
                    log_fn("Chunk text: cache hit")
                return model_dump_safe(state)

    cmd = [
        PYTHON_EXE,
        str(SCRIPT_PATHS["text_to_chunks"]),
        "-i",
        state.paths["text"],
        "-o",
        state.paths["chunks"],
        "-m",
        state.model,
    ]
    run_subprocess_step(state, step_name="Chunk text", cmd=cmd, log_fn=log_fn)
    if cache_enabled(state.env):
        chunks_path = Path(state.paths["chunks"])
        input_path = Path(state.paths["text"])
        if chunks_path.exists() and input_path.exists():
            input_bytes = input_path.read_bytes()
            key = hash_bytes(state.model.encode(), PROMPT_VERSIONS["chunk_text"].encode(), input_bytes)
            cached_path = cache_path(state.job_dir, "chunk_text", key, ".json")
            write_cached(cached_path, chunks_path.read_bytes())
    return model_dump_safe(state)
