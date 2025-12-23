from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from reportlab.pdfgen import canvas

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipeline.graph import run_pipeline_graph  # noqa: E402
from pipeline.state import create_pipeline_state  # noqa: E402
from pipeline.validation import (  # noqa: E402
    validate_chunks_file,
    validate_evidence_file,
    validate_structure_file,
    validate_quiz_file,
)


def create_fixture_pdf(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path))
    text = c.beginText(40, 800)
    lines = [
        "Intro to loops:",
        "A for-loop repeats a block for each item in a sequence.",
        "A while-loop repeats while a condition remains true.",
        "Lists store ordered items and can be indexed from 0.",
        "Common errors include off-by-one conditions.",
    ]
    for line in lines:
        text.textLine(line)
    c.drawText(text)
    c.showPage()
    c.save()


def derive_paths(job_dir: Path, stem: str) -> dict[str, Path]:
    base = stem.strip().replace(" ", "_")
    merged_raw = job_dir / f"{base}_merged_raw.txt"
    merged_cleaned = job_dir / f"{base}_merged_cleaned.txt"
    return {
        "raw_text": merged_raw,
        "cleaned_text": merged_cleaned,
        "text": merged_cleaned,
        "chunks": job_dir / f"{base}_extracted_chunks.json",
        "structure": job_dir / f"{base}_extracted_chunks_structure.json",
        "quiz_json": job_dir / f"{base}_extracted_chunks_structure_quiz.json",
        "quiz_pdf": job_dir / f"{base}_extracted_chunks_structure_quiz.pdf",
        "evidence_json": job_dir / f"{base}_extracted_chunks_structure_evidence.json",
    }


def expected_status(kind: str) -> str:
    return "pending_review" if kind == "class_test" else "ready"


def main() -> None:
    api_key = os.environ.get("CEREBRAS_API_KEY")
    if not api_key:
        raise SystemExit("Missing CEREBRAS_API_KEY for smoke test.")

    data_dir = REPO_ROOT / "interface" / "icodex_webapp" / "data"
    job_dir = data_dir / f"smoke_{int(time.time())}"
    job_dir.mkdir(parents=True, exist_ok=True)

    pdf_path = job_dir / "smoke_fixture.pdf"
    create_fixture_pdf(pdf_path)

    paths = derive_paths(job_dir, "smoke_fixture")
    env = os.environ.copy()
    env["CEREBRAS_API_KEY"] = api_key
    env["PYTHONIOENCODING"] = "utf-8"

    model = os.environ.get("ICODEX_MODEL_NAME", "llama-3.3-70b")
    state = create_pipeline_state(
        job_id=job_dir.name,
        job_dir=str(job_dir),
        source_files=[str(pdf_path)],
        api_key=api_key,
        model=model,
        include_difficulty=False,
        question_limit=10,
        raw_bank_questions=10,
        paths={k: str(v) for k, v in paths.items()},
        env=env,
        cwd=str(REPO_ROOT),
    )

    final_state = run_pipeline_graph(state)

    for key in ("raw_text", "cleaned_text", "chunks", "structure", "quiz_json", "quiz_pdf", "evidence_json"):
        out_path = Path(final_state.paths[key])
        if not out_path.exists():
            raise SystemExit(f"Missing output: {out_path}")

    chunks_result = validate_chunks_file(Path(final_state.paths["chunks"]))
    structure_result = validate_structure_file(Path(final_state.paths["structure"]))
    quiz_result = validate_quiz_file(Path(final_state.paths["quiz_json"]))
    evidence_result = validate_evidence_file(Path(final_state.paths["evidence_json"]))

    if not (chunks_result.valid and structure_result.valid and quiz_result.valid and evidence_result.valid):
        raise SystemExit("Schema validation failed in smoke test.")

    assert expected_status("class_test") == "pending_review"
    assert expected_status("practice_test") == "ready"

    print("Smoke test completed successfully.")


if __name__ == "__main__":
    main()
