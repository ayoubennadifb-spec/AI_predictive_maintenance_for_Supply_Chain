# LangGraph Migration Notes

## Old vs New Orchestration
- Old: `interface/icodex_webapp/app.py` orchestrated subprocess calls in a linear loop.
- New: `pipeline/graph.py` defines a LangGraph DAG with explicit validation, repair, review, and retry loops.
- Legacy scripts remain the source of truth; the graph wraps them to preserve filenames and output shapes.
- `structure_to_questions.Py` now supports `--skip-review`/`--append` for external review/regeneration and defaults to one question per mini-concept.
- Question generation now prioritizes `mini_concepts` exclusively; it only falls back to summary-based nodes when no mini-concepts exist (prevents mixed placement and reviewer mismatches).

## Graph Structure (Current)
1. Extract text (`files_to_text.py`)
2. Rewrite merged text (`text_rewriter.py`)
3. Detect language (sample-based gate)
4. Chunk text (`text_to_chunks.Py`)
5. Validate chunks (schema + normalization)
6. Repair chunks (format-only)
7. Structure text (`chunks_to_structure.py`)
8. Validate structure (schema + evidence + language)
9. Repair structure (LLM JSON repair)
10. Generate questions (`structure_to_questions.Py` with `--skip-review`)
11. Validate quiz (schema + options + language)
12. Repair quiz (LLM JSON repair)
13. Review questions (LLM reviewer + heuristics)
14. Regenerate missing questions (partial regeneration loop)
15. Annotate difficulty (optional)
16. Render PDF

## Pipeline State
Defined in `pipeline/state.py` and used across the graph:
- Core context: `job_id`, `job_dir`, `paths`, `model`, `api_key`
- Content sizing: `mini_concept_count`, `question_target`, `display_limit`
- Validation counters: `*_validation_attempts`, `*_repair_attempts`, `question_review_attempts`
- Review tracking: `question_missing_items`, `questions_missing`, `review_notes`

## Reviewer + Regeneration Loop
- `review_questions` calls the legacy reviewer plus deterministic checks:
  - options count (4), correct answer present, duplicate detection, grounding heuristics.
- Invalid questions are removed from the quiz JSON.
- Missing mini-concepts are regenerated using the legacy LLM prompt.
- The loop is bounded by `question_review_max` and fails loudly if unmet.

## Evidence Sidecar (Practice-Friendly)
- The pipeline now writes an additional evidence map file after the reviewer approves the final question set:
  - `<base>_extracted_chunks_structure_evidence.json`
  - Key in `paths`: `evidence_json`
- This file is **not** part of the quiz JSON schema (no breaking changes) and lets the web app reveal evidence only when appropriate:
  - Practice: return evidence after a student submits an answer.
  - Class/adaptive tests: do not return evidence during the test.
- Important: the filename intentionally does **not** contain `_quiz` to avoid being accidentally picked up by the quiz JSON globbing logic (`*_..._quiz*.json`).

## Validation + Repair Gates
- Pydantic schemas live in `pipeline/schemas.py`.
- Normalization + validation in `pipeline/validation.py`.
- LLM repair uses `pipeline/repair.py` (format/schema only; no new content).
- Language preservation is checked against the cleaned input text.
- `Validate structure` also enforces evidence traceability; if a mini-concept’s `source_evidence` is not found verbatim, it is trimmed and (when possible) repaired deterministically by re-selecting short excerpts from the source text (no invention).

## Caching (Optional)
- Enable with `ICODEX_PIPELINE_CACHE=1`.
- Cache keys use `model + prompt_version + input_hash`.
- Stored under `interface/icodex_webapp/data/<job_id>/.cache/`.

## Resume/Retry
- Rerun the pipeline with the same `job_id` to reuse outputs.
- Validation/repair/review loops are bounded; failures are surfaced with actionable errors.

## Compatibility Guarantees
- Job directory layout and filenames are unchanged.
- API behavior and status transitions are unchanged (class tests still end `pending_review`).
