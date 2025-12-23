from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from pipeline.cache import cache_enabled, cache_path, hash_bytes, read_cached, write_cached
from pipeline.config import PROMPT_VERSIONS
from pipeline.config import PYTHON_EXE, SCRIPT_PATHS
from pipeline.nodes.runner import run_subprocess_step
from pipeline.nodes.runner import record_step
from pipeline.state import PipelineState, model_dump_safe


def rewrite_text(state: PipelineState, log_fn: Optional[Callable[[str], None]] = None) -> dict:
    if cache_enabled(state.env):
        raw_path = Path(state.paths["raw_text"])
        if raw_path.exists():
            raw_bytes = raw_path.read_bytes()
            key = hash_bytes(state.model.encode(), PROMPT_VERSIONS["rewrite_text"].encode(), raw_bytes)
            cached_path = cache_path(state.job_dir, "rewrite_text", key, ".txt")
            cached = read_cached(cached_path)
            if cached is not None:
                Path(state.paths["cleaned_text"]).write_bytes(cached)
                record_step(state, step_name="Rewrite merged text", duration_seconds=0.0, status="success")
                if log_fn:
                    log_fn("Rewrite merged text: cache hit")
                return model_dump_safe(state)

    cmd = [
        PYTHON_EXE,
        str(SCRIPT_PATHS["text_rewriter"]),
        "--input",
        state.paths["raw_text"],
        "--output",
        state.paths["cleaned_text"],
        "--model",
        state.model,
        "--api-key",
        state.api_key,
    ]
    run_subprocess_step(state, step_name="Rewrite merged text", cmd=cmd, log_fn=log_fn)
    if cache_enabled(state.env):
        cleaned_path = Path(state.paths["cleaned_text"])
        if cleaned_path.exists():
            raw_bytes = Path(state.paths["raw_text"]).read_bytes()
            key = hash_bytes(state.model.encode(), PROMPT_VERSIONS["rewrite_text"].encode(), raw_bytes)
            cached_path = cache_path(state.job_dir, "rewrite_text", key, ".txt")
            write_cached(cached_path, cleaned_path.read_bytes())
    return model_dump_safe(state)
