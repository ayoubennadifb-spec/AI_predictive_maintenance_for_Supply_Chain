import argparse
import json
import os
import random
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from reviewer import review_questions

CEREBRAS_API_ENDPOINT = "https://api.cerebras.ai/v1/"


def read_structure_from_file(file_path: str) -> Dict[str, Any]:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("Root must be a JSON object.")
        return data
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found.")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading structure from file: {str(e)}")
        sys.exit(1)


def save_quiz(quiz: Dict[str, Any], output_path: str) -> None:
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(quiz, f, indent=2, ensure_ascii=False)
        print(f"\nQuiz saved to: {output_path}")
    except Exception as e:
        print(f"Error saving file: {str(e)}")
        sys.exit(1)


def _extract_json_block(text: str) -> str:
    content = (text or "").strip()
    if "```json" in content:
        start = content.find("```json") + len("```json")
        end = content.find("```", start)
        if end != -1:
            return content[start:end].strip()
    if "```" in content:
        start = content.find("```") + len("```")
        end = content.find("```", start)
        if end != -1:
            return content[start:end].strip()
    array_start, array_end = content.find("["), content.rfind("]")
    if array_start != -1 and array_end != -1 and array_end > array_start:
        return content[array_start : array_end + 1].strip()
    return content


def ensure_options(questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Guarantee each question has a 4-option list that includes the correct answer."""
    clean: List[Dict[str, Any]] = []
    for q in questions:
        question = str(q.get("question", "")).strip()
        correct = str(q.get("correct_answer", "")).strip() or "Not provided"
        opts = q.get("options") or []
        if not isinstance(opts, list):
            opts = [str(opts)]
        opts = [str(o).strip() for o in opts if str(o).strip()]

        # Ensure correct answer present
        if correct not in opts:
            opts = [correct] + opts

        # Pad with simple distractors
        while len(opts) < 4:
            filler = f"Choice {len(opts)+1}"
            if filler == correct or filler in opts:
                filler += " alt"
            opts.append(filler)

        # Trim to 4 while ensuring correct is present
        if len(opts) > 4:
            if correct not in opts[:4]:
                opts = opts[:3] + [correct]
            else:
                opts = opts[:4]

        # Final safety: if correct was lost, force it back in
        if correct not in opts:
            opts = opts[:3] + [correct]

        random.shuffle(opts)
        clean.append(
            {
                "question": question,
                "options": opts,
                "correct_answer": correct,
            }
        )
    return clean


def clear_existing_questions(node: Any) -> None:
    """Remove previously generated questions to avoid duplicates on re-run."""
    if isinstance(node, dict):
        node.pop("questions", None)
        for key, value in node.items():
            if key == "questions":
                continue
            clear_existing_questions(value)
    elif isinstance(node, list):
        for item in node:
            clear_existing_questions(item)


def _iter_mini_concept_items(structure: Any) -> List[Dict[str, Any]]:
    """
    Collect mini_concepts in order, keeping a reference to the parent concept dict so
    we can attach generated questions at the concept level.
    """
    items: List[Dict[str, Any]] = []

    def walk(node: Any, trail: List[str]) -> None:
        if isinstance(node, dict):
            title = node.get("title") or node.get("name")
            title_str = str(title).strip() if title else ""
            next_trail = trail + [title_str] if title_str else trail

            mini_concepts = node.get("mini_concepts")
            if isinstance(mini_concepts, list):
                for mc in mini_concepts:
                    if not isinstance(mc, dict):
                        continue
                    module_title = next_trail[1] if len(next_trail) > 1 else ""
                    items.append(
                        {
                            "module": module_title,
                            "path": " / ".join([t for t in next_trail if t]),
                            "concept_ref": node,
                            "mini_concept": mc,
                        }
                    )

            for key, value in node.items():
                if key in {"questions", "mini_concepts"}:
                    continue
                walk(value, next_trail)
        elif isinstance(node, list):
            for item in node:
                walk(item, trail)

    walk(structure, [])
    return items


def _iter_summary_items(structure: Any) -> List[Dict[str, Any]]:
    """Fallback: collect titled nodes with summaries when mini_concepts are missing."""
    items: List[Dict[str, Any]] = []

    def walk(node: Any, trail: List[str]) -> None:
        if isinstance(node, dict):
            title = node.get("title") or node.get("name")
            title_str = str(title).strip() if title else ""
            next_trail = trail + [title_str] if title_str else trail

            summary = node.get("summary") or node.get("description") or ""
            if title_str and str(summary).strip():
                module_title = next_trail[1] if len(next_trail) > 1 else ""
                items.append(
                    {
                        "module": module_title,
                        "path": " / ".join([t for t in next_trail if t]),
                        "concept_ref": node,
                        "mini_concept": {
                            "title": title_str,
                            "summary": str(summary).strip(),
                            "keywords": node.get("keywords") or [],
                            "source_evidence": [],
                        },
                    }
                )

            for key, value in node.items():
                if key == "questions":
                    continue
                walk(value, next_trail)
        elif isinstance(node, list):
            for item in node:
                walk(item, trail)

    walk(structure, [])
    return items


def _select_balanced(items: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    """
    Select up to `limit` items, distributed across modules to avoid only using the first section.
    Deterministic ordering.
    """
    limit = max(0, int(limit or 0))
    if limit == 0 or not items:
        return []

    by_module: Dict[str, List[Dict[str, Any]]] = {}
    module_order: List[str] = []
    for item in items:
        module = (item.get("module") or "").strip() or "General"
        if module not in by_module:
            by_module[module] = []
            module_order.append(module)
        by_module[module].append(item)

    desired = min(limit, len(items))
    selected: List[Dict[str, Any]] = []

    base = desired // max(1, len(module_order))
    extra = desired % max(1, len(module_order))

    # First pass: take a quota per module
    for module in module_order:
        quota = base + (1 if extra > 0 else 0)
        if extra > 0:
            extra -= 1
        take = min(quota, len(by_module[module]))
        selected.extend(by_module[module][:take])
        by_module[module] = by_module[module][take:]

    remaining = desired - len(selected)

    # Second pass: round-robin fill remaining from modules with leftover items
    while remaining > 0:
        progressed = False
        for module in module_order:
            if not by_module[module]:
                continue
            selected.append(by_module[module].pop(0))
            remaining -= 1
            progressed = True
            if remaining <= 0:
                break
        if not progressed:
            break

    return selected[:desired]


_CODE_HINT_RE = re.compile(
    r"[`{}\[\]();]|==|!=|<=|>=|->|\b("
    r"def|class|for|while|if|elif|else|try|except|finally|return|yield|lambda|"
    r"import|from|with|async|await|dict|list|set|tuple|range|len"
    r")\b",
    re.IGNORECASE,
)
_DOC_STRUCTURE_RE = re.compile(
    r"\b("
    r"table\s+of\s+contents|toc|preface|appendix|acknowledg(e|ment)s?|"
    r"references|bibliography|index"
    r")\b",
    re.IGNORECASE,
)
_STRONG_NON_TECH_RE = re.compile(
    r"\b("
    r"history|creator|created\s+by|invent(ed|or)|guido|year|released?|timeline|origin|born|"
    r"popularity|popular|philosophy|zen\s+of\s+python"
    r")\b",
    re.IGNORECASE,
)
_MILD_NON_TECH_RE = re.compile(
    r"\b("
    r"introduction|overview|get(ting)?\s+started|background|about\s+python|why\s+python"
    r")\b",
    re.IGNORECASE,
)
_PROGRAMMING_TOPIC_RE = re.compile(
    r"\b("
    r"loop|loops|iteration|iterator|generator|comprehension|function|functions|parameter|argument|"
    r"scope|closure|recursion|dictionary|dictionaries|mapping|hash|mutable|immutable|"
    r"exception|error|typeerror|valueerror|syntaxerror"
    r")\b",
    re.IGNORECASE,
)


def _combined_item_text(item: Dict[str, Any]) -> str:
    mc = item.get("mini_concept") or {}
    evidence = mc.get("source_evidence") or mc.get("sourceEvidence") or []
    if not isinstance(evidence, list):
        evidence = [str(evidence)]
    keywords = mc.get("keywords") or []
    if not isinstance(keywords, list):
        keywords = [str(keywords)]
    parts = [
        item.get("path", ""),
        mc.get("title", ""),
        mc.get("summary", ""),
        " ".join([str(k) for k in keywords if str(k).strip()]),
        " ".join([str(e) for e in evidence if str(e).strip()]),
    ]
    return " ".join([str(p) for p in parts if str(p).strip()])


def _technicality_score(text: str) -> float:
    score = 0.0
    if _CODE_HINT_RE.search(text):
        score += 1.0
    if _PROGRAMMING_TOPIC_RE.search(text):
        score += 0.6
    if _MILD_NON_TECH_RE.search(text):
        score -= 0.4
    if _STRONG_NON_TECH_RE.search(text):
        score -= 1.2
    if _DOC_STRUCTURE_RE.search(text):
        score -= 2.0
    return score


def _should_exclude_from_technical_quiz(text: str) -> bool:
    if _DOC_STRUCTURE_RE.search(text):
        return True
    if _STRONG_NON_TECH_RE.search(text) and not _CODE_HINT_RE.search(text):
        return True
    if _MILD_NON_TECH_RE.search(text) and not (_CODE_HINT_RE.search(text) or _PROGRAMMING_TOPIC_RE.search(text)):
        return True
    return False


def _select_balanced_technical(items: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    """
    Prefer technical items (code/semantics/constraints) and avoid trivia/history when possible.
    Falls back to the full item set if filtering would leave too few items.
    """
    limit = max(0, int(limit or 0))
    if limit == 0 or not items:
        return []

    scored: List[tuple[bool, float, int, Dict[str, Any]]] = []
    for idx, item in enumerate(items):
        text = _combined_item_text(item)
        scored.append((_should_exclude_from_technical_quiz(text), _technicality_score(text), idx, item))

    preferred: List[tuple[float, int, Dict[str, Any]]] = [
        (score, idx, item) for exclude, score, idx, item in scored if not exclude
    ]
    min_needed = min(limit, max(8, limit // 4))
    if len(preferred) < min_needed:
        preferred = [(score, idx, item) for _exclude, score, idx, item in scored]

    by_module: Dict[str, List[tuple[float, int, Dict[str, Any]]]] = {}
    module_order: List[str] = []
    for score, idx, item in preferred:
        module = (item.get("module") or "").strip() or "General"
        if module not in by_module:
            by_module[module] = []
            module_order.append(module)
        by_module[module].append((score, idx, item))

    for module in module_order:
        by_module[module].sort(key=lambda t: (-t[0], t[1]))

    desired = min(limit, sum(len(v) for v in by_module.values()))
    selected: List[Dict[str, Any]] = []

    base = desired // max(1, len(module_order))
    extra = desired % max(1, len(module_order))

    for module in module_order:
        quota = base + (1 if extra > 0 else 0)
        if extra > 0:
            extra -= 1
        take = min(quota, len(by_module[module]))
        selected.extend([t[2] for t in by_module[module][:take]])
        by_module[module] = by_module[module][take:]

    remaining = desired - len(selected)
    while remaining > 0:
        progressed = False
        for module in module_order:
            if not by_module[module]:
                continue
            selected.append(by_module[module].pop(0)[2])
            remaining -= 1
            progressed = True
            if remaining <= 0:
                break
        if not progressed:
            break

    return selected[:desired]


def generate_questions_batch(
    items: List[Dict[str, Any]],
    api_key: str,
    model: str,
    timeout: int,
) -> Optional[List[Dict[str, Any]]]:
    """
    Generate exactly one question per input item, grounded ONLY in the provided evidence/summary.

    Input items must include:
      - index (int)
      - path (string)
      - title (string)
      - summary (string)
      - keywords (string[])
      - evidence (string[])
    """
    prompt = (
        "SYSTEM ROLE:\n"
        "You are a deterministic, context-grounded multiple-choice quiz writer.\n"
        "You must use ONLY the provided item content (title/summary/keywords/evidence).\n"
        "If a fact is not stated or clearly implied there, you must NOT use it.\n\n"
        "TASK:\n"
        "For each item in the input JSON array, generate EXACTLY ONE multiple-choice question that can be answered\n"
        "using ONLY that item's evidence/summary.\n\n"
        "SUBJECT FOCUS (CRITICAL):\n"
        "- Each question must target the specific mini-concept in the item (not general-world trivia).\n"
        "- The correct answer must be directly supported by the item's evidence or summary.\n"
        "- Do NOT ask anything that requires external background knowledge to answer.\n\n"
        "TECHNICAL QUIZ TARGET (CRITICAL):\n"
        "- Write technical questions about behavior, semantics, syntax, constraints, edge cases, or correct usage.\n"
        "- Prefer questions that require reasoning (e.g., output/exception, which snippet is valid, which condition holds).\n"
        "- When the item includes constraints/exceptions/pitfalls, test those (not generic definitions).\n"
        "- Avoid trivia/biography/history (people, dates, origin, popularity) even if you know it.\n"
        '- Avoid generic prompts like "What is Python?" or "Why is Python popular?".\n\n'
        "DEPTH RULES (PREFER WHEN POSSIBLE):\n"
        "- Prefer understanding/application over shallow recall.\n"
        "- Use ONE of these styles when the item supports it:\n"
        "  1) Apply a rule/definition to a minimal scenario.\n"
        "  2) Choose the best explanation/purpose of a step, term, or method.\n"
        "  3) Distinguish between two closely related terms in the item.\n"
        "  4) Infer the consequence of changing a condition stated in the item.\n"
        "- If the evidence contains code or symbols, include a short code snippet in the question.\n"
        "- Keep it answerable from the item; do not introduce new facts.\n\n"
        "IMPORTANT:\n"
        "- Generate exactly ONE question per input item (never more).\n"
        "- NEVER skip an item. If evidence is weak, generate a simple, on-topic question using the summary/keywords.\n"
        "- The quiz bank is capped at 100 questions elsewhere; do not try to exceed the input length.\n\n"
        "LANGUAGE RULES (CRITICAL):\n"
        "- Detect the language of each item from its summary/evidence.\n"
        "- Write the question, options, and correct_answer in that same language.\n"
        "- Do NOT translate the content into English. Keep accents and punctuation.\n\n"
        "ABSOLUTE OUTPUT RULES:\n"
        "1) Output ONLY a single JSON array. No prose. No headings. No code fences.\n"
        "2) Output array length MUST equal input array length and preserve order.\n"
        "3) Each output element MUST be an object with EXACTLY these keys:\n"
        '   - "index" (integer, copied from input)\n'
        '   - "question" (string)\n'
        '   - "options" (array of EXACTLY 4 DISTINCT strings)\n'
        '   - "correct_answer" (string that EXACTLY matches one of the options)\n'
        "4) Do NOT include any additional keys.\n\n"
        "QUALITY RULES:\n"
        "- Be straight to the point: no prefaces like \"According to the text\".\n"
        "- Keep questions short and specific (<= 32 words).\n"
        "- Keep each option short (<= 10 words) and parallel in style.\n"
        "- Use at least one keyword (verbatim) in the question when available.\n"
        "- Prefer subject-specific wording from the evidence/summary (avoid generic phrasing).\n"
        "- Wrong options must be plausible but clearly incorrect given the evidence.\n"
        '- Do NOT use "All of the above" or "None of the above".\n'
        '- Do NOT output generic options like "Introduction", "Content", "Idea", "None".\n'
        '- Do NOT ask document-structure questions like "What is available?" unless the evidence explicitly teaches that.\n'
        "- Do NOT ask about anything not supported by the summary/keywords/evidence.\n"
        "- If evidence is limited, ask a question that tests understanding of the summary (do not invent facts).\n\n"
        f"INPUT:\n{json.dumps(items, ensure_ascii=False)}\n"
    )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "stream": False,
    }

    try:
        response = requests.post(
            f"{CEREBRAS_API_ENDPOINT}chat/completions",
            headers=headers,
            json=payload,
            timeout=timeout,
        )
        if response.status_code != 200:
            print(f"    API Error: {response.status_code} - {response.text}")
            return None
        data = response.json()
        content = data["choices"][0]["message"]["content"].strip()
        parsed = json.loads(_extract_json_block(content))
        if not isinstance(parsed, list):
            print("    LLM returned non-list JSON for batch.")
            return None
        if len(parsed) != len(items):
            print(f"    LLM returned {len(parsed)} items; expected {len(items)}. Retrying with smaller batches.")
            return None
        required = {"index", "question", "options", "correct_answer"}
        for elem in parsed:
            if not isinstance(elem, dict) or not required.issubset(elem.keys()):
                print("    LLM returned invalid item shape for batch. Retrying with smaller batches.")
                return None
        return parsed
    except Exception as e:
        print(f"    Batch generation failed: {str(e)}")
        return None


MAX_REVIEW_ROUNDS = 5


def collect_flat_questions(structure: Any) -> List[Dict[str, Any]]:
    """Return flattened list of questions with metadata for reviewer and removals."""
    flattened: List[Dict[str, Any]] = []

    def walk(node: Any, trail: List[str]) -> None:
        if isinstance(node, dict):
            title = node.get("title") or node.get("name")
            title_str = str(title).strip() if title else ""
            next_trail = trail + [title_str] if title_str else trail
            questions = node.get("questions")
            if isinstance(questions, list):
                for question in questions:
                    flattened.append(
                        {
                            "question": question,
                            "node": node,
                            "path": " / ".join([t for t in next_trail if t]),
                        }
                    )
            for key, value in node.items():
                if key == "questions":
                    continue
                walk(value, next_trail)
        elif isinstance(node, list):
            for item in node:
                walk(item, trail)

    walk(structure, [])
    return flattened


def remove_invalid_questions_from_flat(flat: List[Dict[str, Any]], invalid_indices: List[int]) -> int:
    """Remove the invalid questions (by reference) from the structure."""
    removed = 0
    for idx in sorted(set(invalid_indices), reverse=True):
        if idx < 0 or idx >= len(flat):
            continue
        entry = flat[idx]
        container = entry["node"].get("questions") or []
        target_question = entry["question"]
        for stored in list(container):
            if stored is target_question:
                container.remove(stored)
                removed += 1
                break
    return removed


def generate_questions_from_seed(
    seed_items: List[Dict[str, Any]],
    question_target: int,
    api_key: str,
    model: str,
    timeout: int,
    batch_size: int,
    delay: float,
    allow_repeat: bool = False,
) -> int:
    """Generate up to `question_target` new questions from the provided seed items."""
    if question_target <= 0 or not seed_items:
        return 0

    if allow_repeat:
        candidate_target = max(question_target * 2, question_target + 40)
        candidate_limit = min(len(seed_items), candidate_target)
    else:
        candidate_target = min(len(seed_items), question_target)
        candidate_limit = candidate_target

    selected = _select_balanced_technical(seed_items, candidate_limit)

    if allow_repeat and selected and len(selected) < candidate_target:
        seed_cycle = selected[:]
        while len(selected) < candidate_target:
            selected.append(dict(seed_cycle[len(selected) % len(seed_cycle)]))

    if not selected:
        return 0

    generated = 0

    def build_llm_inputs(batch_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        inputs: List[Dict[str, Any]] = []
        for local_idx, item in enumerate(batch_items):
            mc = item.get("mini_concept") or {}
            evidence = mc.get("source_evidence") or mc.get("sourceEvidence") or []
            if not isinstance(evidence, list):
                evidence = [str(evidence)]
            keywords = mc.get("keywords") or []
            if not isinstance(keywords, list):
                keywords = [str(keywords)]
            inputs.append(
                {
                    "index": local_idx,
                    "path": item.get("path", ""),
                    "title": str(mc.get("title", "")).strip(),
                    "summary": str(mc.get("summary", "")).strip(),
                    "keywords": [str(k).strip() for k in keywords[:8] if str(k).strip()],
                    "evidence": [str(e).strip() for e in evidence[:3] if str(e).strip()],
                }
            )
        return inputs

    def process_items(batch_items: List[Dict[str, Any]]) -> None:
        nonlocal generated
        if not batch_items or generated >= question_target:
            return
        remaining = question_target - generated
        batch_items = batch_items[:remaining]
        if not batch_items:
            return

        llm_inputs = build_llm_inputs(batch_items)
        out = generate_questions_batch(llm_inputs, api_key=api_key, model=model, timeout=timeout)
        if not out:
            if len(batch_items) > 1:
                mid = len(batch_items) // 2
                process_items(batch_items[:mid])
                process_items(batch_items[mid:])
            return

        by_index: Dict[int, Dict[str, Any]] = {}
        for q in out:
            if not isinstance(q, dict):
                continue
            try:
                i = int(q.get("index"))
            except Exception:
                continue
            by_index[i] = q

        if len(by_index) != len(batch_items):
            if len(batch_items) > 1:
                mid = len(batch_items) // 2
                process_items(batch_items[:mid])
                process_items(batch_items[mid:])
            return

        for i in range(len(batch_items)):
            if generated >= question_target:
                break
            q = by_index.get(i)
            if not q:
                continue
            cleaned = ensure_options(
                [
                    {
                        "question": q.get("question", ""),
                        "options": q.get("options", []),
                        "correct_answer": q.get("correct_answer", ""),
                    }
                ]
            )
            if not cleaned:
                continue
            if not str(cleaned[0].get("id") or "").strip():
                cleaned[0]["id"] = uuid.uuid4().hex
            concept_ref = batch_items[i]["concept_ref"]
            concept_ref.setdefault("questions", []).append(cleaned[0])
            generated += 1

    cursor = 0
    batch_num = 1
    while cursor < len(selected) and generated < question_target:
        remaining = question_target - generated
        take = min(batch_size, remaining)
        batch_items = selected[cursor : cursor + take]
        cursor += take
        print(f"  Batch {batch_num} ({len(batch_items)} items)...")
        before = generated
        process_items(batch_items)
        after = generated
        print(f"    +{after - before} (total {generated}/{question_target})")
        batch_num += 1
        time.sleep(delay)

    return generated


def ensure_valid_quiz(
    structure: Dict[str, Any],
    seed_items: List[Dict[str, Any]],
    target: int,
    api_key: str,
    model: str,
    timeout: int,
    batch_size: int,
    delay: float,
    allow_repeat: bool = False,
) -> None:
    """Loop until the quiz has `target` reviewed questions or we hit the max review passes."""
    attempts = 0
    while attempts < MAX_REVIEW_ROUNDS:
        flat = collect_flat_questions(structure)
        current = len(flat)
        if current < target:
            missing = target - current
            print(f"Generating {missing} replacement question(s) after review...")
            generated = generate_questions_from_seed(
                seed_items,
                missing,
                api_key,
                model,
                timeout,
                batch_size,
                delay,
                allow_repeat=allow_repeat,
            )
            if generated == 0:
                print("Unable to generate replacement questions; stopping review loop.")
                break
            continue

        review = review_questions(flat, api_key, model, timeout)
        invalid = sorted(set(review.get("invalid_indices") or []))
        if not invalid:
            print("Quiz reviewer approved all questions.")
            return
        removed = remove_invalid_questions_from_flat(flat, invalid)
        print(f"Quiz reviewer removed {removed} question(s): {review.get('notes', 'See reviewer notes.')}")
        attempts += 1

    if attempts >= MAX_REVIEW_ROUNDS:
        print("Reached maximum review rounds; proceeding with remaining quiz.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate quiz from structured text using Cerebras LLM.")
    parser.add_argument("-i", "--input", default="hibernate_extracted_chunks_structure.json")
    parser.add_argument("-o", "--output")
    parser.add_argument("-m", "--model", default="llama3.1-8b")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument(
        "--max-questions",
        type=int,
        default=100,
        help="Maximum total questions for the whole quiz (default: 100).",
    )
    parser.add_argument(
        "--skip-review",
        action="store_true",
        help="Skip the reviewer loop (for external review/regeneration pipelines).",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append new questions without clearing existing ones.",
    )
    parser.add_argument(
        "--allow-repeat",
        action="store_true",
        help="Allow multiple questions per mini-concept when exceeding available items.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=20,
        help="Questions per LLM request (default: 20).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.2,
        help="Seconds to sleep between LLM requests (default: 0.2).",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("CEREBRAS_API_KEY"),
        help="Cerebras API key (defaults to CEREBRAS_API_KEY env var).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    api_key = args.api_key or os.environ.get("CEREBRAS_API_KEY")
    if not api_key:
        print(
            "Error: No Cerebras API key provided. "
            "Set the CEREBRAS_API_KEY environment variable or pass --api-key."
        )
        sys.exit(1)

    input_file = args.input
    output_file = args.output or (Path(input_file).stem + "_quiz.json")

    max_questions = max(1, int(args.max_questions or 1))
    batch_size = max(1, int(args.batch_size or 1))
    delay = max(0.0, float(args.delay or 0.0))

    print("Quiz Generation (Cerebras Edition)")
    print("=" * 60)
    print(f"Input file: {input_file}")
    print(f"Output file: {output_file}")
    print(f"Model: {args.model}")
    print(f"Max questions: {max_questions}")
    print("=" * 60)

    structure = read_structure_from_file(input_file)
    if not args.append:
        clear_existing_questions(structure)

    # Prefer mini_concepts (with evidence) for in-context question generation.
    # Only fall back to summary items when mini_concepts are missing entirely.
    seed_items = _iter_mini_concept_items(structure)
    if not seed_items:
        seed_items = _iter_summary_items(structure)

    if not seed_items:
        print("No suitable nodes found for question generation. No questions generated.")
        save_quiz(structure, output_file)
        return


    target = min(max_questions, len(seed_items))
    if target <= 0:
        print("No eligible mini-concepts found for question generation.")
        save_quiz(structure, output_file)
        return

    print(f"Generating {target} question(s) (raw bank, max 100)...")

    generated = generate_questions_from_seed(
        seed_items,
        target,
        api_key,
        args.model,
        args.timeout,
        batch_size,
        delay,
        allow_repeat=args.allow_repeat,
    )
    if generated < target:
        print(f"\nERROR: Quiz generation incomplete. Generated {generated}/{target} question(s).")
        sys.exit(1)

    if not args.skip_review:
        ensure_valid_quiz(
            structure,
            seed_items,
            target,
            api_key,
            args.model,
            args.timeout,
            batch_size,
            delay,
            allow_repeat=args.allow_repeat,
        )

    total_questions = len(collect_flat_questions(structure))
    if total_questions < target:
        print(f"\nERROR: Only {total_questions}/{target} questions remain after review.")
        sys.exit(1)

    save_quiz(structure, output_file)
    print(f"\nQuiz generation complete. Validated {total_questions}/{target} question(s).")

if __name__ == "__main__":
    main()
