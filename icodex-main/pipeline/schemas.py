from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

try:  # Pydantic v2
    from pydantic import ConfigDict, field_validator, model_validator  # type: ignore
except Exception:  # pragma: no cover
    ConfigDict = None
    field_validator = None
    model_validator = None
    from pydantic import validator, root_validator  # type: ignore


class SchemaBase(BaseModel):
    if ConfigDict is not None:
        model_config = ConfigDict(extra="forbid", populate_by_name=True)
    else:  # pragma: no cover
        class Config:
            extra = "forbid"
            allow_population_by_field_name = True


class ChunkItem(SchemaBase):
    id: int
    text: str
    char_count: int
    word_count: int


class ChunkOutput(SchemaBase):
    total_chunks: int
    chunks: List[ChunkItem]

    if model_validator is not None:
        @model_validator(mode="after")
        def _check_total(self):  # type: ignore[override]
            if self.total_chunks != len(self.chunks):
                raise ValueError("total_chunks does not match chunks length")
            return self
    else:  # pragma: no cover
        @root_validator
        def _check_total(cls, values):  # type: ignore[override]
            total = values.get("total_chunks")
            chunks = values.get("chunks") or []
            if total is not None and total != len(chunks):
                raise ValueError("total_chunks does not match chunks length")
            return values


class MiniConcept(SchemaBase):
    title: str
    summary: str
    keywords: List[str]
    source_evidence: List[str] = Field(alias="sourceEvidence")


class Question(SchemaBase):
    question: str
    options: List[str]
    correct_answer: str = Field(alias="correctAnswer")
    id: Optional[str] = None
    difficulty: Optional[str] = None
    answer: Optional[str] = None

    if model_validator is not None:
        @model_validator(mode="before")
        def _coerce_answer(cls, values):  # type: ignore[override]
            if not isinstance(values, dict):
                return values
            if "correct_answer" not in values and "correctAnswer" not in values:
                if "answer" in values:
                    values["correct_answer"] = values.get("answer")
            return values
    else:  # pragma: no cover
        @root_validator(pre=True)
        def _coerce_answer(cls, values):  # type: ignore[override]
            if not isinstance(values, dict):
                return values
            if "correct_answer" not in values and "correctAnswer" not in values:
                if "answer" in values:
                    values["correct_answer"] = values.get("answer")
            return values


class EvidenceItem(SchemaBase):
    id: Optional[str] = None
    question: str
    position: Optional[str] = None
    mini_concept_title: Optional[str] = None
    evidence: List[str]


class EvidenceSidecar(SchemaBase):
    version: int
    questions: List[EvidenceItem]


class Concept(SchemaBase):
    title: str
    summary: str
    mini_concepts: List[MiniConcept] = Field(alias="miniConcepts")
    questions: Optional[List[Question]] = None


class MiniModule(SchemaBase):
    title: str
    summary: str
    concepts: List[Concept]


class Module(SchemaBase):
    title: str
    summary: str
    mini_modules: List[MiniModule] = Field(alias="miniModules")


class Course(SchemaBase):
    title: str
    description: str
    modules: List[Module]


class CourseWrapper(SchemaBase):
    course: Course
