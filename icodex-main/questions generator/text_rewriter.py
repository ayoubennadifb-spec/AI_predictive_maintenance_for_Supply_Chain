from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import requests

CEREBRAS_API_ENDPOINT = "https://api.cerebras.ai/v1/"

PROMPT_TEMPLATE = """SYSTEM ROLE:\nYou are an editorial LLM that reforms an educational transcript without losing any facts.\n\nTASK:\nGiven the raw merged text from multiple course materials, rewrite it into a cleaner, well-structured version. The rewritten text must:\n- Keep every important fact, definition, and example. Do not drop or invent details.\n- Remove near-duplicate sentences or repetitions while preserving meaning.\n- Improve formatting (headings, bullet-style sentences) to read smoothly, but do not omit content.\n- Preserve the original order of sections.\n- Avoid injecting summaries or new interpretation beyond clarifications.\n\nOUTPUT RULES:\n- Respond with the rewritten text only, no JSON, no headings, no explanations.\n\nINPUT TEXT:\n{text}\n"""


def read_text(file_path: Path) -> str:
    try:
        return file_path.read_text(encoding="utf-8")
    except Exception as exc:
        raise SystemExit(f"Failed to read {file_path}: {exc}") from exc


def write_text(file_path: Path, text: str) -> None:
    file_path.write_text(text, encoding="utf-8")


def call_rewriter(text: str, api_key: str, model: str, timeout: int) -> str:
    prompt = PROMPT_TEMPLATE.format(text=text.strip())
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
    except requests.RequestException as exc:
        raise SystemExit(f"Rewriter request failed: {exc}") from exc

    if response.status_code != 200:
        raise SystemExit(f"Rewriter API error: {response.status_code} {response.text}")

    data = response.json()
    content = data.get("choices", [{}])[0].get("message", {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise SystemExit("Rewriter did not return valid text.")
    return content.strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rewrite merged course text with an LLM.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="llama3.1-8b")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument(
        "--api-key",
        default=os.environ.get("CEREBRAS_API_KEY"),
        help="Cerebras API key (defaults to CEREBRAS_API_KEY env var).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.api_key:
        raise SystemExit("Missing Cerebras API key for the text rewriter.")

    source_text = read_text(args.input)
    if not source_text.strip():
        raise SystemExit(f"Input {args.input} is empty.")

    rewritten = call_rewriter(source_text, args.api_key, args.model, args.timeout)
    write_text(args.output, rewritten)
    print(f"Rewritten text saved to: {args.output}")


if __name__ == "__main__":
    main()
