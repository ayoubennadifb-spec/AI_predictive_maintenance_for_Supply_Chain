from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from pipeline.errors import PipelineStepError
from pipeline.language import detect_language, languages_match
from pipeline.nodes.runner import record_step
from pipeline.state import PipelineState, model_dump_safe
from pipeline.validation import persist_if_repaired, validate_structure_file


_WS_RE = re.compile(r"\s+", re.UNICODE)
_NON_WORD_RE = re.compile(r"[^\w\s]+", re.UNICODE)
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)
_PARA_SPLIT_RE = re.compile(r"\n{2,}", re.UNICODE)


def _iter_mini_concepts(node):
    if isinstance(node, dict):
        mini = node.get("mini_concepts")
        if isinstance(mini, list):
            for item in mini:
                if isinstance(item, dict):
                    yield item
        for key, value in node.items():
            if key == "mini_concepts":
                continue
            yield from _iter_mini_concepts(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_mini_concepts(item)


def _collect_language_text(node) -> str:
    parts = []
    if isinstance(node, dict):
        for key in ("title", "summary", "description"):
            if key in node and isinstance(node[key], str):
                parts.append(node[key])
        if isinstance(node.get("keywords"), list):
            parts.extend([str(k) for k in node["keywords"] if str(k).strip()])
        if isinstance(node.get("source_evidence"), list):
            parts.extend([str(e) for e in node["source_evidence"] if str(e).strip()])
        for key, value in node.items():
            if key in {"keywords", "source_evidence"}:
                continue
            parts.append(_collect_language_text(value))
    elif isinstance(node, list):
        for item in node:
            parts.append(_collect_language_text(item))
    return " ".join([p for p in parts if p])


def _normalize_space(text: str) -> str:
    text = (text or "").replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    text = _WS_RE.sub(" ", text).strip().lower()
    return text


def _normalize_wordish(text: str) -> str:
    text = _normalize_space(text)
    text = _NON_WORD_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    return text


def _snippet_in_sources(
    snippet: str,
    *,
    sources_space: list[str],
    sources_wordish: list[str],
) -> bool:
    snippet = str(snippet or "").strip()
    if not snippet:
        return False

    snippet_space = _normalize_space(snippet)
    if snippet_space:
        for src in sources_space:
            if snippet_space in src:
                return True

    snippet_wordish = _normalize_wordish(snippet)
    if snippet_wordish:
        for src in sources_wordish:
            if snippet_wordish in src:
                return True

    return False


def _token_set(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text or "") if t.strip()}


def _extract_paragraph_containing(source: str, phrase: str) -> str:
    phrase = str(phrase or "").strip()
    if len(phrase) < 3:
        return ""

    try:
        match = re.search(re.escape(phrase), source, flags=re.IGNORECASE)
    except re.error:
        match = None

    if not match:
        return ""

    start = source.rfind("\n\n", 0, match.start())
    if start == -1:
        start = 0
    else:
        start += 2

    end = source.find("\n\n", match.end())
    if end == -1:
        end = len(source)

    paragraph = source[start:end].strip()
    if len(paragraph) < 20:
        return ""
    return paragraph


def _rank_paragraphs(source: str, concept_tokens: set[str], *, limit: int = 3) -> list[str]:
    if not concept_tokens:
        return []

    parts = [p.strip() for p in _PARA_SPLIT_RE.split(source or "") if p.strip()]
    scored: list[tuple[int, str]] = []
    for p in parts:
        score = len(_token_set(p).intersection(concept_tokens))
        if score <= 0:
            continue
        scored.append((score, p))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [p for _score, p in scored[: max(0, int(limit))]]


def _extract_evidence_for_mini_concept(
    mc: dict,
    *,
    sources_original: list[str],
    sources_space: list[str],
    sources_wordish: list[str],
    max_items: int = 2,
    max_chars: int = 420,
) -> list[str]:
    title = str(mc.get("title") or "").strip()
    keywords = mc.get("keywords") or []
    if not isinstance(keywords, list):
        keywords = [keywords]
    phrases: list[str] = []
    if title:
        phrases.append(title)
    for kw in keywords:
        kw_str = str(kw).strip()
        if kw_str and kw_str.lower() not in {p.lower() for p in phrases}:
            phrases.append(kw_str)

    concept_tokens = _token_set(" ".join(phrases))
    candidates: list[str] = []

    for source in sources_original:
        for phrase in phrases:
            paragraph = _extract_paragraph_containing(source, phrase)
            if paragraph:
                candidates.append(paragraph)
                break
        if candidates:
            break

    if not candidates:
        for source in sources_original:
            ranked = _rank_paragraphs(source, concept_tokens, limit=max_items)
            candidates.extend(ranked)
            if candidates:
                break

    evidence: list[str] = []
    seen_norm = set()
    for cand in candidates:
        snippet = str(cand or "").strip()
        if not snippet:
            continue
        if len(snippet) > max_chars:
            snippet = snippet[:max_chars].rstrip()
        norm = _normalize_space(snippet)
        if norm in seen_norm:
            continue
        seen_norm.add(norm)
        if _snippet_in_sources(snippet, sources_space=sources_space, sources_wordish=sources_wordish):
            evidence.append(snippet)
        if len(evidence) >= max_items:
            break

    return evidence


def validate_structure(state: PipelineState, log_fn: Optional[Callable[[str], None]] = None) -> dict:
    start = time.time()
    state.structure_validation_attempts += 1
    state.structure_regen_required = False
    path = Path(state.paths.get("structure", ""))
    result = validate_structure_file(path)

    if not result.valid:
        state.structure_validation_failed = True
        state.structure_regen_required = False
        error = "; ".join(result.errors) or "Structure validation failed"
        state.last_error = error
        if log_fn:
            log_fn(f"Validate structure failed: {error}")
        record_step(
            state,
            step_name="Validate structure",
            duration_seconds=round(time.time() - start, 2),
            status="failed",
            error=error,
        )
        if state.structure_validation_attempts >= state.structure_validation_max:
            raise PipelineStepError(f"Validate structure failed: {error}", state)
        return model_dump_safe(state)

    persist_if_repaired(path, result)
    data: Dict[str, Any] = result.data or {}

    mini_concepts = list(_iter_mini_concepts(data))
    state.mini_concept_count = len(mini_concepts)
    state.question_target = min(state.raw_bank_questions, state.mini_concept_count)

    # Evidence grounding check against cleaned text
    cleaned_path = Path(state.paths.get("cleaned_text", ""))
    raw_path = Path(state.paths.get("raw_text", ""))
    source_texts: list[str] = []
    for candidate in (cleaned_path, raw_path):
        if not candidate.exists():
            continue
        try:
            source_texts.append(candidate.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            continue

    sources_space = [_normalize_space(text) for text in source_texts if str(text).strip()]
    sources_wordish = [_normalize_wordish(text) for text in source_texts if str(text).strip()]

    missing_concepts = 0
    removed_snippets = 0
    total_snippets = 0
    repaired_concepts = 0
    first_missing_example: Optional[Dict[str, str]] = None
    missing_mini_concepts: list[dict] = []
    for mc in mini_concepts:
        evidence = mc.get("source_evidence") or mc.get("sourceEvidence") or []
        if not isinstance(evidence, list):
            evidence = [evidence]
        evidence_strs = [str(s).strip() for s in evidence if str(s).strip()]
        if not evidence_strs:
            missing_concepts += 1
            if first_missing_example is None:
                first_missing_example = {
                    "title": str(mc.get("title") or "").strip(),
                    "snippet": "",
                }
            continue

        matched: list[str] = []
        for snippet in evidence_strs:
            total_snippets += 1
            if _snippet_in_sources(
                snippet,
                sources_space=sources_space,
                sources_wordish=sources_wordish,
            ):
                matched.append(snippet)
            else:
                removed_snippets += 1

        if not matched:
            missing_concepts += 1
            missing_mini_concepts.append(mc)
            if first_missing_example is None:
                first_missing_example = {
                    "title": str(mc.get("title") or "").strip(),
                    "snippet": str(evidence_strs[0] or "").strip(),
                }
        elif len(matched) != len(evidence_strs):
            mc["source_evidence"] = matched

    # Attempt deterministic evidence repair for untraceable mini-concepts (format-only; no invention).
    if missing_mini_concepts and source_texts:
        sources_original = source_texts
        for mc in list(missing_mini_concepts):
            repaired = _extract_evidence_for_mini_concept(
                mc,
                sources_original=sources_original,
                sources_space=sources_space,
                sources_wordish=sources_wordish,
            )
            if repaired:
                mc["source_evidence"] = repaired
                repaired_concepts += 1

        if repaired_concepts:
            # Re-check only those that were previously missing.
            still_missing: list[dict] = []
            for mc in missing_mini_concepts:
                evidence = mc.get("source_evidence") or []
                if not isinstance(evidence, list):
                    evidence = [evidence]
                evidence_strs = [str(s).strip() for s in evidence if str(s).strip()]
                if not evidence_strs:
                    still_missing.append(mc)
                    continue
                if not any(
                    _snippet_in_sources(s, sources_space=sources_space, sources_wordish=sources_wordish)
                    for s in evidence_strs
                ):
                    still_missing.append(mc)

            if still_missing:
                missing_mini_concepts = still_missing
                missing_concepts = len(still_missing)
                if first_missing_example is None and still_missing:
                    mc0 = still_missing[0]
                    ev0 = mc0.get("source_evidence") or []
                    if not isinstance(ev0, list):
                        ev0 = [ev0]
                    first_missing_example = {
                        "title": str(mc0.get("title") or "").strip(),
                        "snippet": str(ev0[0] if ev0 else "").strip(),
                    }
            else:
                missing_mini_concepts = []
                missing_concepts = 0

    language_error = None
    if state.language:
        lang_text = _collect_language_text(data)
        lang, _conf = detect_language(lang_text)
        if lang and not languages_match(state.language, lang):
            language_error = f"Structure language '{lang}' does not match '{state.language}'"

    if missing_concepts or language_error:
        state.structure_validation_failed = True
        state.structure_regen_required = True
        error_parts = []
        if missing_concepts:
            error_parts.append(f"Evidence mismatch ({missing_concepts} mini_concepts untraceable)")
        if language_error:
            error_parts.append(language_error)
        error = "; ".join(error_parts) or "Structure validation failed"
        state.last_error = error
        if log_fn:
            if first_missing_example is not None:
                ex_title = first_missing_example.get("title") or ""
                ex_snippet = first_missing_example.get("snippet") or ""
                if ex_snippet:
                    log_fn(
                        f"Evidence example not found in source: {ex_snippet[:120]}"
                        + (f" (mini_concept='{ex_title}')" if ex_title else "")
                    )
            log_fn(f"Validate structure failed: {error}")
        record_step(
            state,
            step_name="Validate structure",
            duration_seconds=round(time.time() - start, 2),
            status="failed",
            error=error,
        )
        if state.structure_validation_attempts >= state.structure_validation_max:
            raise PipelineStepError(f"Validate structure failed: {error}", state)
        return model_dump_safe(state)

    if removed_snippets or repaired_concepts:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        if log_fn:
            if removed_snippets:
                log_fn(f"Validate structure: trimmed {removed_snippets}/{total_snippets} untraceable evidence snippet(s).")
            if repaired_concepts:
                log_fn(f"Validate structure: repaired evidence for {repaired_concepts} mini_concept(s).")

    state.structure_validation_failed = False
    if log_fn:
        log_fn(
            f"Validate structure: OK (mini_concepts={state.mini_concept_count}, "
            f"target_questions={state.question_target})"
        )
    record_step(
        state,
        step_name="Validate structure",
        duration_seconds=round(time.time() - start, 2),
        status="success",
    )
    return model_dump_safe(state)
