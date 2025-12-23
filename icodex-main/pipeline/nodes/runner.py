from __future__ import annotations

import subprocess
import time
from typing import Callable, Iterable, Optional

from pipeline.errors import PipelineStepError
from pipeline.state import PipelineState, PipelineStep


def _coerce_cmd(cmd: Iterable[str]) -> list[str]:
    return [str(part) for part in cmd]


def _error_message(stdout: str, stderr: str) -> str:
    message = (stderr or "").strip() or (stdout or "").strip()
    return message or "unknown error"


def run_subprocess_step(
    state: PipelineState,
    *,
    step_name: str,
    cmd: Iterable[str],
    log_fn: Optional[Callable[[str], None]] = None,
) -> PipelineState:
    if log_fn:
        log_fn(f"{step_name}...")
    start = time.time()
    try:
        result = subprocess.run(
            _coerce_cmd(cmd),
            cwd=state.cwd or None,
            env=state.env or None,
            capture_output=True,
            text=True,
        )
    except Exception as exc:
        duration = round(time.time() - start, 2)
        step = PipelineStep(name=step_name, duration_seconds=duration, status="failed", error=str(exc))
        state.metrics.steps.append(step)
        state.metrics.status = "failed"
        state.last_error = str(exc)
        if log_fn:
            log_fn(f"{step_name} failed: {exc}")
        raise PipelineStepError(f"{step_name} failed: {exc}", state) from exc

    duration = round(time.time() - start, 2)
    stdout = result.stdout or ""
    stderr = result.stderr or ""

    if result.returncode != 0:
        err_msg = _error_message(stdout, stderr)
        step = PipelineStep(name=step_name, duration_seconds=duration, status="failed", error=err_msg)
        state.metrics.steps.append(step)
        state.metrics.status = "failed"
        state.last_error = err_msg
        if log_fn:
            log_fn(f"{step_name} failed: {err_msg}")
        raise PipelineStepError(f"{step_name} failed: {err_msg}", state)

    step = PipelineStep(name=step_name, duration_seconds=duration, status="success")
    state.metrics.steps.append(step)
    if log_fn and stdout.strip():
        log_fn(stdout.strip())
    if log_fn and stderr.strip():
        log_fn(stderr.strip())
    return state


def record_step(
    state: PipelineState,
    *,
    step_name: str,
    duration_seconds: float,
    status: str = "success",
    error: Optional[str] = None,
) -> None:
    state.metrics.steps.append(
        PipelineStep(
            name=step_name,
            duration_seconds=duration_seconds,
            status=status,
            error=error,
        )
    )
