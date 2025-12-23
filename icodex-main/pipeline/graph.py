from __future__ import annotations

from typing import Callable, Optional

from langgraph.graph import END, StateGraph

from pipeline.errors import PipelineStepError
from pipeline.nodes.annotate_difficulty import annotate_difficulty
from pipeline.nodes.chunk_text import chunk_text
from pipeline.nodes.detect_language import detect_language_node
from pipeline.nodes.extract_text import extract_text
from pipeline.nodes.generate_questions import generate_questions
from pipeline.nodes.regenerate_questions import regenerate_questions
from pipeline.nodes.repair_chunks import repair_chunks
from pipeline.nodes.repair_quiz import repair_quiz
from pipeline.nodes.repair_structure import repair_structure
from pipeline.nodes.render_pdf import render_pdf
from pipeline.nodes.rewrite_text import rewrite_text
from pipeline.nodes.review_questions import review_questions
from pipeline.nodes.structure_text import structure_text
from pipeline.nodes.validate_chunks import validate_chunks
from pipeline.nodes.validate_quiz import validate_quiz
from pipeline.nodes.validate_structure import validate_structure
from pipeline.state import PipelineMetrics, PipelineState, iso_utc_now, model_dump_safe


def _coerce_state(value) -> PipelineState:
    if isinstance(value, PipelineState):
        return value
    return PipelineState(**value)


def _wrap(node_fn, log_fn: Optional[Callable[[str], None]] = None):
    def _node(state):
        coerced = _coerce_state(state)
        return node_fn(coerced, log_fn=log_fn)

    return _node


def _route_after_chunks(state: PipelineState) -> str:
    return "repair_chunks" if state.chunk_validation_failed else "structure_text"


def _route_after_structure(state: PipelineState) -> str:
    if state.structure_validation_failed:
        return "structure_text" if state.structure_regen_required else "repair_structure"
    return "generate_questions"


def _route_after_quiz(state: PipelineState) -> str:
    if state.quiz_validation_failed:
        return "generate_questions" if state.quiz_regen_required else "repair_quiz"
    return "review_questions"


def _route_after_review(state: PipelineState) -> str:
    if state.question_review_failed:
        return "regenerate_questions"
    if state.include_difficulty:
        return "annotate_difficulty"
    return "render_pdf"


def build_graph(log_fn: Optional[Callable[[str], None]] = None):
    graph = StateGraph(PipelineState)

    graph.add_node("extract_text", _wrap(extract_text, log_fn))
    graph.add_node("rewrite_text", _wrap(rewrite_text, log_fn))
    graph.add_node("detect_language", _wrap(detect_language_node, log_fn))
    graph.add_node("chunk_text", _wrap(chunk_text, log_fn))
    graph.add_node("validate_chunks", _wrap(validate_chunks, log_fn))
    graph.add_node("repair_chunks", _wrap(repair_chunks, log_fn))
    graph.add_node("structure_text", _wrap(structure_text, log_fn))
    graph.add_node("validate_structure", _wrap(validate_structure, log_fn))
    graph.add_node("repair_structure", _wrap(repair_structure, log_fn))
    graph.add_node("generate_questions", _wrap(generate_questions, log_fn))
    graph.add_node("validate_quiz", _wrap(validate_quiz, log_fn))
    graph.add_node("repair_quiz", _wrap(repair_quiz, log_fn))
    graph.add_node("review_questions", _wrap(review_questions, log_fn))
    graph.add_node("regenerate_questions", _wrap(regenerate_questions, log_fn))
    graph.add_node("annotate_difficulty", _wrap(annotate_difficulty, log_fn))
    graph.add_node("render_pdf", _wrap(render_pdf, log_fn))

    graph.set_entry_point("extract_text")
    graph.add_edge("extract_text", "rewrite_text")
    graph.add_edge("rewrite_text", "detect_language")
    graph.add_edge("detect_language", "chunk_text")
    graph.add_edge("chunk_text", "validate_chunks")

    graph.add_conditional_edges(
        "validate_chunks",
        _route_after_chunks,
        {
            "repair_chunks": "repair_chunks",
            "structure_text": "structure_text",
        },
    )
    graph.add_edge("repair_chunks", "validate_chunks")

    graph.add_edge("structure_text", "validate_structure")
    graph.add_conditional_edges(
        "validate_structure",
        _route_after_structure,
        {
            "repair_structure": "repair_structure",
            "structure_text": "structure_text",
            "generate_questions": "generate_questions",
        },
    )
    graph.add_edge("repair_structure", "validate_structure")

    graph.add_edge("generate_questions", "validate_quiz")
    graph.add_conditional_edges(
        "validate_quiz",
        _route_after_quiz,
        {
            "repair_quiz": "repair_quiz",
            "generate_questions": "generate_questions",
            "review_questions": "review_questions",
        },
    )
    graph.add_edge("repair_quiz", "validate_quiz")

    graph.add_conditional_edges(
        "review_questions",
        _route_after_review,
        {
            "regenerate_questions": "regenerate_questions",
            "annotate_difficulty": "annotate_difficulty",
            "render_pdf": "render_pdf",
        },
    )
    graph.add_edge("regenerate_questions", "review_questions")
    graph.add_edge("annotate_difficulty", "render_pdf")
    graph.add_edge("render_pdf", END)

    return graph.compile()


def _finalize_metrics(metrics: PipelineMetrics, status: str) -> None:
    metrics.completed_at = iso_utc_now()
    metrics.status = status
    metrics.duration_seconds = round(sum(step.duration_seconds for step in metrics.steps), 2)


def run_pipeline_graph(
    state: PipelineState, *, log_fn: Optional[Callable[[str], None]] = None
) -> PipelineState:
    """
    Execute the LangGraph pipeline. Each node wraps a legacy script call, so
    outputs and filenames remain identical to the subprocess-based pipeline.
    """
    app = build_graph(log_fn=log_fn)
    try:
        result = app.invoke(state)
    except PipelineStepError as exc:
        failed_state = _coerce_state(exc.state)
        _finalize_metrics(failed_state.metrics, status="failed")
        exc.state = failed_state
        raise

    final_state = _coerce_state(result)
    _finalize_metrics(final_state.metrics, status="success")
    return final_state


def state_to_dict(state: PipelineState) -> dict:
    return model_dump_safe(state)
