from __future__ import annotations

import json
from typing import Optional

import requests

CEREBRAS_API_ENDPOINT = "https://api.cerebras.ai/v1/"


def extract_json_block(text: str) -> str:
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
    start_index = content.find("{")
    end_index = content.rfind("}")
    if start_index != -1 and end_index != -1 and end_index > start_index:
        return content[start_index : end_index + 1]
    start_index = content.find("[")
    end_index = content.rfind("]")
    if start_index != -1 and end_index != -1 and end_index > start_index:
        return content[start_index : end_index + 1]
    return content


def repair_json_with_llm(
    raw_text: str,
    *,
    schema_hint: str,
    api_key: str,
    model: str,
    timeout: int = 300,
) -> Optional[str]:
    prompt = (
        "SYSTEM ROLE:\n"
        "You are a deterministic JSON repair tool.\n\n"
        "TASK:\n"
        "Fix the INPUT JSON so it strictly matches the REQUIRED SCHEMA.\n"
        "You MUST preserve all existing content and wording. Do NOT invent new facts.\n"
        "You may only:\n"
        "- Remove extra wrapper text/code fences\n"
        "- Rename keys to match the schema\n"
        "- Coerce types (string -> list with same content)\n"
        "- Drop invalid fields\n"
        "- Use empty strings or empty lists ONLY when a required field is completely missing\n\n"
        "OUTPUT RULES:\n"
        "- Output ONLY valid JSON (no markdown, no commentary)\n"
        "- Preserve the original language and wording\n\n"
        f"REQUIRED SCHEMA:\n{schema_hint}\n\n"
        f"INPUT JSON:\n{raw_text}\n"
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
    except Exception:
        return None

    if response.status_code != 200:
        return None

    try:
        data = response.json()
    except Exception:
        return None

    content = data.get("choices", [{}])[0].get("message", {}).get("content")
    if not isinstance(content, str):
        return None
    extracted = extract_json_block(content)
    if not extracted.strip():
        return None
    try:
        json.loads(extracted)
    except Exception:
        return None
    return extracted
