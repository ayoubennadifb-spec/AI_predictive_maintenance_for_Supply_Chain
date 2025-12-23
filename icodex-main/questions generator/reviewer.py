import json
from typing import Any, Dict, List, Set, Tuple

import requests

REVIEW_PROMPT = """SYSTEM ROLE:\nYou are a strict quiz quality reviewer.\n\nTASK:\nGiven a list of quiz questions, identify the ones that are vague, unrelated to the source item, trivial, or repetitive compared to the rest of the bank. The entire question set should stay on-topic and preserve pedagogical value.\n\nOUTPUT RULES:\nReturn ONLY a JSON object with exactly two keys:\n- "invalid_indices": an array of zero-based indexes pointing to the questions that should be removed.\n- "notes": a short string describing the general issue if any invalid questions were found, or "OK" if everything looks good.\nNO additional text or formatting is allowed.\n\nINPUT QUESTIONS:\n{}\n"""


def _extract_json_block(text: str) -> str:
    if not text:
        return text
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and start < end:
        return text[start : end + 1]
    return text


def review_questions(
    flat_questions: List[Dict[str, Any]],
    api_key: str,
    model: str,
    timeout: int = 300,
    ) -> Dict[str, Any]:
    if not flat_questions:
        return {"invalid_indices": [], "notes": "OK"}
    if not api_key:
        print("Quiz reviewer skipped: missing API key.")
        return {"invalid_indices": [], "notes": "OK"}

    # Local duplicate detector before invoking the LLM.
    def normalize(q: Dict[str, Any]) -> str:
        text = str(q.get("question", ""))[:400].strip().lower()
        options = q.get("options") or []
        opts_norm = " | ".join(sorted([str(o).strip().lower() for o in options if str(o).strip()]))
        return f"{text} || {opts_norm}"

    duplicate_indices: List[int] = []
    seen: Dict[str, int] = {}
    for idx, entry in enumerate(flat_questions):
        question = entry.get("question", {})
        sig = normalize(question)
        if not sig:
            continue
        if sig in seen:
            duplicate_indices.append(idx)
        else:
            seen[sig] = idx

    payload_items: List[Dict[str, Any]] = []
    for idx, entry in enumerate(flat_questions):
        question = entry.get("question", {})
        payload_items.append(
            {
                "index": idx,
                "path": entry.get("path", ""),
                "question": str(question.get("question", ""))[:1200],
                "options": [str(o) for o in (question.get("options") or [])][:4],
                "correct_answer": str(
                    question.get("correct_answer") or question.get("answer") or ""
                ),
            }
        )

    prompt = REVIEW_PROMPT.format(json.dumps(payload_items, ensure_ascii=False))
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
            "https://api.cerebras.ai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=timeout,
        )
        content = response.text.strip()
        if response.status_code != 200:
            print(
                "Quiz reviewer API error",
                response.status_code,
                response.text[:400],
            )
            return {"invalid_indices": [], "notes": "API error"}
        data = json.loads(content)
        message_content = data["choices"][0]["message"]["content"].strip()
        parsed_text = _extract_json_block(message_content)
        parsed = json.loads(parsed_text)
    except Exception as err:  # noqa: BLE001
        print("Quiz reviewer failed:", err)
        return {"invalid_indices": [], "notes": "Review skipped"}

    invalid = parsed.get("invalid_indices") or []
    if not isinstance(invalid, list):
        invalid = []
    merged_invalid = sorted(set(invalid + duplicate_indices))
    notes = parsed.get("notes", "OK")
    if duplicate_indices:
        if notes and notes != "OK":
            notes = f"{notes} | Removed duplicates"
        else:
            notes = "Removed duplicates"
    return {"invalid_indices": merged_invalid, "notes": notes}
