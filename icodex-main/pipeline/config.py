from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_DIR = REPO_ROOT / "questions generator"

PYTHON_EXE = sys.executable

SCRIPT_PATHS = {
    "files_to_text": PIPELINE_DIR / "files_to_text.py",
    "text_rewriter": PIPELINE_DIR / "text_rewriter.py",
    "text_to_chunks": PIPELINE_DIR / "text_to_chunks.Py",
    "chunks_to_structure": PIPELINE_DIR / "chunks_to_structure.py",
    "structure_to_questions": PIPELINE_DIR / "structure_to_questions.Py",
    "difficulty_assessor": PIPELINE_DIR / "difficulty_assessor.py",
    "quiz_to_pdf": PIPELINE_DIR / "quiz_to_pdf.py",
}

DEFAULT_RAW_BANK_QUESTIONS = 100
DEFAULT_MAX_MINI_CONCEPTS = 120
DEFAULT_VALIDATION_MAX = 2
DEFAULT_REPAIR_MAX = 2
DEFAULT_REVIEW_MAX = 3
CACHE_ENV_FLAG = "ICODEX_PIPELINE_CACHE"
PROMPT_VERSIONS = {
    "rewrite_text": "v1",
    "chunk_text": "v1",
    "structure_text": "v1",
    "generate_questions": "v1",
}
