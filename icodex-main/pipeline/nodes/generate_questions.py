from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from pipeline.cache import cache_enabled, cache_path, hash_bytes, read_cached, write_cached
from pipeline.config import PROMPT_VERSIONS
from pipeline.config import PYTHON_EXE, SCRIPT_PATHS
from pipeline.errors import PipelineStepError
from pipeline.nodes.runner import run_subprocess_step
from pipeline.nodes.runner import record_step
from pipeline.state import PipelineState, model_dump_safe


def generate_questions(state: PipelineState, log_fn: Optional[Callable[[str], None]] = None) -> dict:
    target = state.question_target or 0
    if target <= 0:
        raise PipelineStepError("No mini-concepts available for question generation.", state)
    if cache_enabled(state.env) and state.question_review_attempts == 0:
        input_path = Path(state.paths["structure"])
        if input_path.exists():
            input_bytes = input_path.read_bytes()
            key = hash_bytes(
                state.model.encode(),
                PROMPT_VERSIONS["generate_questions"].encode(),
                input_bytes,
                str(target).encode(),
            )
            cached_path = cache_path(state.job_dir, "generate_questions", key, ".json")
            cached = read_cached(cached_path)
            if cached is not None:
                Path(state.paths["quiz_json"]).write_bytes(cached)
                record_step(state, step_name="Generate questions", duration_seconds=0.0, status="success")
                if log_fn:
                    log_fn("Generate questions: cache hit")
                return model_dump_safe(state)

    cmd = [
        PYTHON_EXE,
        str(SCRIPT_PATHS["structure_to_questions"]),
        "-i",
        state.paths["structure"],
        "-o",
        state.paths["quiz_json"],
        "--max-questions",
        str(target),
        "--skip-review",
        "-m",
        state.model,
    ]
    run_subprocess_step(state, step_name="Generate questions", cmd=cmd, log_fn=log_fn)
    if cache_enabled(state.env):
        quiz_path = Path(state.paths["quiz_json"])
        input_path = Path(state.paths["structure"])
        if quiz_path.exists() and input_path.exists():
            input_bytes = input_path.read_bytes()
            key = hash_bytes(
                state.model.encode(),
                PROMPT_VERSIONS["generate_questions"].encode(),
                input_bytes,
                str(target).encode(),
            )
            cached_path = cache_path(state.job_dir, "generate_questions", key, ".json")
            write_cached(cached_path, quiz_path.read_bytes())
    return model_dump_safe(state)
