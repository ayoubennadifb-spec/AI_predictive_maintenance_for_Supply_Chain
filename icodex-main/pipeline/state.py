from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

try:  # Pydantic v2
    from pydantic import ConfigDict  # type: ignore
except Exception:  # pragma: no cover
    ConfigDict = None


def iso_utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def model_dump_safe(model: BaseModel, **kwargs) -> Dict:
    if hasattr(model, "model_dump"):
        return model.model_dump(**kwargs)
    return model.dict(**kwargs)  # type: ignore[call-arg]


class PipelineStep(BaseModel):
    name: str
    duration_seconds: float
    status: str = "success"
    error: Optional[str] = None

    if ConfigDict is not None:
        model_config = ConfigDict(arbitrary_types_allowed=True)
    else:  # pragma: no cover
        class Config:
            arbitrary_types_allowed = True


class PipelineMetrics(BaseModel):
    steps: List[PipelineStep] = Field(default_factory=list)
    started_at: str = Field(default_factory=iso_utc_now)
    completed_at: Optional[str] = None
    status: Optional[str] = None
    duration_seconds: Optional[float] = None

    if ConfigDict is not None:
        model_config = ConfigDict(arbitrary_types_allowed=True)
    else:  # pragma: no cover
        class Config:
            arbitrary_types_allowed = True


class PipelineState(BaseModel):
    job_id: str
    job_dir: str
    source_files: List[str]
    api_key: str
    model: str
    include_difficulty: bool
    question_limit: int
    raw_bank_questions: int = 100
    display_limit: int = 100
    paths: Dict[str, str] = Field(default_factory=dict)
    env: Dict[str, str] = Field(default_factory=dict)
    cwd: str = ""
    metrics: PipelineMetrics = Field(default_factory=PipelineMetrics)
    language: Optional[str] = None
    language_confidence: Optional[float] = None
    mini_concept_count: int = 0
    question_target: int = 0
    chunk_validation_attempts: int = 0
    chunk_validation_max: int = 2
    chunk_repair_attempts: int = 0
    chunk_repair_max: int = 2
    chunk_validation_failed: bool = False
    structure_validation_attempts: int = 0
    structure_validation_max: int = 2
    structure_repair_attempts: int = 0
    structure_repair_max: int = 2
    structure_validation_failed: bool = False
    structure_regen_required: bool = False
    quiz_validation_attempts: int = 0
    quiz_validation_max: int = 2
    quiz_repair_attempts: int = 0
    quiz_repair_max: int = 2
    quiz_validation_failed: bool = False
    quiz_regen_required: bool = False
    question_review_attempts: int = 0
    question_review_max: int = 3
    question_review_failed: bool = False
    questions_missing: int = 0
    question_missing_items: List[Dict[str, str]] = Field(default_factory=list)
    review_notes: Optional[str] = None
    last_error: Optional[str] = None

    if ConfigDict is not None:
        model_config = ConfigDict(arbitrary_types_allowed=True)
    else:  # pragma: no cover
        class Config:
            arbitrary_types_allowed = True


def create_pipeline_state(
    *,
    job_id: str,
    job_dir: str,
    source_files: List[str],
    api_key: str,
    model: str,
    include_difficulty: bool,
    question_limit: int,
    raw_bank_questions: int,
    paths: Dict[str, str],
    env: Dict[str, str],
    cwd: str,
    question_review_max: Optional[int] = None,
) -> PipelineState:
    try:
        from pipeline.config import DEFAULT_REPAIR_MAX, DEFAULT_REVIEW_MAX, DEFAULT_VALIDATION_MAX
    except Exception:  # pragma: no cover
        DEFAULT_REPAIR_MAX = 2
        DEFAULT_REVIEW_MAX = question_review_max
        DEFAULT_VALIDATION_MAX = 2
    display_limit = max(1, min(100, int(question_limit or 100)))
    return PipelineState(
        job_id=job_id,
        job_dir=job_dir,
        source_files=source_files,
        api_key=api_key,
        model=model,
        include_difficulty=include_difficulty,
        question_limit=question_limit,
        raw_bank_questions=raw_bank_questions,
        display_limit=display_limit,
        paths=paths,
        env=env,
        cwd=cwd,
        metrics=PipelineMetrics(),
        question_review_max=DEFAULT_REVIEW_MAX if question_review_max is None else question_review_max,
        chunk_validation_max=DEFAULT_VALIDATION_MAX,
        chunk_repair_max=DEFAULT_REPAIR_MAX,
        structure_validation_max=DEFAULT_VALIDATION_MAX,
        structure_repair_max=DEFAULT_REPAIR_MAX,
        quiz_validation_max=DEFAULT_VALIDATION_MAX,
        quiz_repair_max=DEFAULT_REPAIR_MAX,
    )
