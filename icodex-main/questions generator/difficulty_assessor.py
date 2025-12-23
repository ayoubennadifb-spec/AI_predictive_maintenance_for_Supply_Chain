"""
Annotate quiz JSON with difficulty metadata using the Cerebras Chat Completions API.

Pipeline role:
  - Reads a quiz JSON (same format produced by structure_to_questions.Py)
  - Adds difficulty metadata to each question (easy|medium|hard)
  - Writes an updated quiz JSON (by default to <input>_difficulty.json, or in-place)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests

CEREBRAS_API_ENDPOINT = "https://api.cerebras.ai/v1/"


def load_quiz(path: Path) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        print(f"Failed to read quiz JSON: {exc}")
        sys.exit(1)


def save_quiz(data: Dict[str, Any], path: Path) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Annotated quiz saved to: {path}")
    except Exception as exc:
        print(f"Failed to write quiz JSON: {exc}")
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
    obj_start, obj_end = content.find("{"), content.rfind("}")
    if obj_start != -1 and obj_end != -1 and obj_end > obj_start:
        return content[obj_start : obj_end + 1].strip()
    return content


def call_llm_batch(
    items: list[dict[str, Any]],
    api_key: str,
    model: str,
    timeout: int,
) -> Optional[list[dict[str, Any]]]:
    prompt = (
        "You are a deterministic difficulty-rating engine for multiple-choice quiz questions.\n"
        "Return ONLY valid JSON (no markdown, no extra text).\n\n"
        "TASK:\n"
        "Given an input JSON array of items (each with a question and answer choices),\n"
        "classify each item's difficulty as exactly one of: \"easy\", \"medium\", \"hard\".\n"
        "Return a JSON array with the SAME length and SAME order as the input.\n\n"
        "ASSUMPTIONS:\n"
        "- Rate difficulty for a typical learner who has studied the same material the question comes from.\n"
        "- Base the rating on the cognitive steps required by the question itself; do NOT rely on outside knowledge.\n\n"
        "LANGUAGE:\n"
        "- Write the rationale in the same language as the question.\n\n"
        "OUTPUT RULES (STRICT):\n"
        "1) Output ONLY a single JSON array.\n"
        "2) Output length MUST equal input length.\n"
        "3) Each output element MUST be an object with EXACTLY these keys:\n"
        "   - \"index\" (integer, copied from input)\n"
        "   - \"difficulty\" (string: easy|medium|hard)\n"
        "   - \"confidence\" (number between 0 and 1)\n"
        "   - \"rationale\" (string, 1 sentence max)\n"
        "4) Do NOT include any additional keys.\n"
        "5) Do NOT invent or assume missing content.\n\n"
        "RUBRIC:\n"
        "easy: direct recall/recognition; 1 step; minimal computation.\n"
        "medium: 2-3 steps or light application/computation; plausible distractors.\n"
        "hard: 3+ steps, combines concepts, non-obvious inference, or tricky distractors.\n\n"
        "CONFIDENCE:\n"
        "0.85-1.00 clear match; 0.60-0.84 some uncertainty; 0.35-0.59 ambiguous; 0.10-0.34 unclear.\n\n"
        f"INPUT JSON ARRAY:\n{json.dumps(items, ensure_ascii=False)}\n"
    )

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0, "stream": False}

    try:
        resp = requests.post(
            f"{CEREBRAS_API_ENDPOINT}chat/completions",
            headers=headers,
            json=payload,
            timeout=timeout,
        )
        if resp.status_code != 200:
            print(f"API error {resp.status_code}: {resp.text}")
            return None
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        parsed = json.loads(_extract_json_block(content))
        if isinstance(parsed, list):
            return parsed
        print("LLM returned non-list JSON for batch.")
        return None
    except Exception as exc:
        print(f"LLM call failed: {exc}")
        return None


def _iter_question_refs(node: Any) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []

    def walk(n: Any) -> None:
        if isinstance(n, dict):
            questions = n.get("questions")
            if isinstance(questions, list):
                for q in questions:
                    if isinstance(q, dict):
                        refs.append(q)
            for k, v in n.items():
                if k != "questions":
                    walk(v)
        elif isinstance(n, list):
            for item in n:
                walk(item)

    walk(node)
    return refs


def annotate_questions(
    quiz: Dict[str, Any],
    api_key: str,
    model: str,
    timeout: int,
    delay: float,
    batch_size: int,
) -> int:
    refs = _iter_question_refs(quiz)
    to_rate: list[dict[str, Any]] = [q for q in refs if not q.get("difficulty")]
    if not to_rate:
        return 0

    batch_size = max(1, int(batch_size or 1))
    delay = max(0.0, float(delay or 0.0))
    updated = 0

    for start in range(0, len(to_rate), batch_size):
        batch = to_rate[start : start + batch_size]
        items: list[dict[str, Any]] = []
        for idx, q in enumerate(batch):
            items.append(
                {
                    "index": idx,
                    "question": str(q.get("question", ""))[:800],
                    "options": (q.get("options") or [])[:8],
                    "correct_answer": str(q.get("correct_answer", ""))[:200],
                }
            )

        rated = call_llm_batch(items, api_key=api_key, model=model, timeout=timeout)
        if not rated:
            time.sleep(delay)
            continue

        by_index: dict[int, dict[str, Any]] = {}
        for item in rated:
            if not isinstance(item, dict):
                continue
            try:
                i = int(item.get("index"))
            except Exception:
                continue
            by_index[i] = item

        for idx, q in enumerate(batch):
            item = by_index.get(idx)
            if not item:
                continue
            diff = item.get("difficulty")
            if isinstance(diff, str) and diff.strip():
                q["difficulty"] = diff.strip().lower()
            if "confidence" in item:
                q["difficulty_confidence"] = item.get("confidence")
            if "rationale" in item:
                q["difficulty_rationale"] = item.get("rationale")
            updated += 1

        time.sleep(delay)

    return updated


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Annotate quiz questions with difficulty using an LLM.")
    parser.add_argument("-i", "--input", default="hibernate_extracted_chunks_structure_quiz.json", help="Input quiz JSON.")
    parser.add_argument(
        "-o",
        "--output",
        help="Output path. Defaults to <input>_difficulty.json (same directory as input).",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Write back to the input file instead of creating a new file.",
    )
    parser.add_argument("-m", "--model", default="llama3.1-8b")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--delay", type=float, default=0.2, help="Seconds to sleep between batch calls.")
    parser.add_argument("--batch-size", type=int, default=20, help="Questions per LLM request.")
    parser.add_argument(
        "--api-key",
        default=os.environ.get("CEREBRAS_API_KEY"),
        help="Cerebras API key (or set CEREBRAS_API_KEY env var).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.api_key:
        print("Error: API key is required (pass --api-key or set CEREBRAS_API_KEY).")
        sys.exit(1)

    input_path = Path(args.input)
    if args.in_place:
        output_path = input_path
    else:
        output_path = Path(args.output) if args.output else input_path.with_name(f"{input_path.stem}_difficulty.json")

    quiz = load_quiz(input_path)
    print("Annotating questions with difficulty...")
    updated = annotate_questions(
        quiz=quiz,
        api_key=args.api_key,
        model=args.model,
        timeout=args.timeout,
        delay=args.delay,
        batch_size=args.batch_size,
    )
    save_quiz(quiz, output_path)
    print(f"Done. Updated {updated} question(s).")


if __name__ == "__main__":
    main()
