"""
Smart text chunker using the Cerebras Chat Completions API.

Pipeline role:
  - Reads extracted text from a file
  - Uses an LLM to insert a delimiter at semantic boundaries
  - Saves chunked output to JSON for downstream steps
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

import requests

CEREBRAS_API_ENDPOINT = "https://api.cerebras.ai/v1/"


def read_text_file(file_path: str) -> str:
    """Read text from a file."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found.")
        sys.exit(1)
    except Exception as exc:
        print(f"Error reading file: {exc}")
        sys.exit(1)


def _choose_delimiter(text: str) -> str:
    for _ in range(10):
        delim = f"<<<ICODEX_CHUNK_DELIMITER_{uuid.uuid4().hex}>>>"
        if delim not in text:
            return delim
    return "<<<ICODEX_CHUNK_DELIMITER_FALLBACK>>>"


def chunk_text_with_llm(
    text: str,
    api_key: str,
    model: str = "llama3.1-8b",
    max_chunk_size: int = 2000,
    timeout: int = 300,
) -> list[str]:
    print("Analyzing text structure with LLM...")
    print(f"Text length: {len(text)} characters\n")

    num_chunks_est = max(1, len(text) // max_chunk_size + 1)
    delimiter = _choose_delimiter(text)

    prompt = f"""You are a deterministic TEXT-CHUNKING engine.

Goal: split the INPUT TEXT into semantic chunks for downstream processing.

OUTPUT FORMAT (STRICT):
1) Output ONLY the original text, split into chunks in the original order.
2) Separate chunks using this exact delimiter string (output it exactly as-is, on its own line):
{delimiter}
3) Do NOT output anything else (no numbering, no JSON, no markdown, no commentary).

CONTENT RULES:
- Preserve the original wording. Do not paraphrase, summarize, translate, or correct.
- Do not invent or omit content.
- Keep original order. Only insert the delimiter between chunks.

BOUNDARY RULES:
- Prefer splitting at major headings/section breaks, then blank lines, then paragraphs.
- Never split inside a sentence.
- Keep lists/tables/code blocks together when possible.
- Keep Example/Explanation/Solution sequences together.
- Keep definitions/rules with their immediate constraints/exceptions and examples when possible.
- Keep formulas with nearby variable/term definitions when possible.

SIZE TARGET:
- Aim for chunks around {max_chunk_size} characters.
- Target about {num_chunks_est} chunks total (can be +/- 2 to respect boundaries).

INPUT TEXT:
{text}
"""

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
            print(f"API Error: {response.status_code}")
            print(response.text)
            sys.exit(1)

        data = response.json()
        content = data["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            print("Error: Model returned non-text content.")
            sys.exit(1)
        content = content.strip()

        chunks = [chunk.strip() for chunk in content.split(delimiter) if chunk.strip()]
        if not chunks:
            print("Error: Model did not return any valid chunks.")
            print("Raw LLM output:")
            print(content)
            sys.exit(1)

        return chunks
    except requests.exceptions.RequestException as exc:
        print(f"Network error: {exc}")
        sys.exit(1)
    except Exception as exc:
        print(f"Unexpected error: {exc}")
        sys.exit(1)


def save_chunks(chunks: list[str], output_path: str) -> dict:
    try:
        output_data = {
            "total_chunks": len(chunks),
            "chunks": [
                {
                    "id": i + 1,
                    "text": chunk,
                    "char_count": len(chunk),
                    "word_count": len(chunk.split()),
                }
                for i, chunk in enumerate(chunks)
            ],
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        print(f"\nChunks saved to: {output_path}")
        return output_data
    except Exception as exc:
        print(f"Error saving file: {exc}")
        sys.exit(1)


def display_statistics(chunks_data: dict) -> None:
    print("\n" + "=" * 60)
    print("CHUNKING STATISTICS")
    print("=" * 60)

    total = int(chunks_data.get("total_chunks", 0) or 0)
    print(f"Total chunks: {total}")
    if total <= 0:
        return

    char_counts = [c["char_count"] for c in chunks_data["chunks"]]
    word_counts = [c["word_count"] for c in chunks_data["chunks"]]

    print("\nCharacter counts:")
    print(f"  Avg: {sum(char_counts) / total:.0f}")
    print(f"  Min: {min(char_counts)}")
    print(f"  Max: {max(char_counts)}")

    print("\nWord counts:")
    print(f"  Avg: {sum(word_counts) / total:.0f}")
    print(f"  Min: {min(word_counts)}")
    print(f"  Max: {max(word_counts)}")

    print("\nPreview of first chunk:")
    first_chunk = chunks_data["chunks"][0]["text"]
    print("  " + first_chunk[:200].replace("\n", " ") + "...")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smart text chunker using Cerebras LLM.")
    parser.add_argument("-i", "--input", default="hibernate_extracted.txt")
    parser.add_argument("-o", "--output")
    parser.add_argument("-s", "--chunk-size", type=int, default=2000)
    parser.add_argument("-m", "--model", default="llama3.1-8b")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument(
        "--api-key",
        default=os.environ.get("CEREBRAS_API_KEY"),
        help="Cerebras API key (defaults to CEREBRAS_API_KEY env var).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    api_key = args.api_key
    if not api_key:
        print(
            "Error: No Cerebras API key provided.\n"
            "Set the CEREBRAS_API_KEY environment variable or pass --api-key."
        )
        sys.exit(1)
    if args.chunk_size <= 0:
        print("Error: Chunk size must be a positive integer.")
        sys.exit(1)

    input_file = args.input
    output_file = args.output or (Path(input_file).stem + "_chunks.json")

    print("Smart Text Chunker (Cerebras Edition)")
    print("=" * 60)
    print(f"Input file: {input_file}")
    print(f"Output file: {output_file}")
    print(f"Chunk size: {args.chunk_size}")
    print(f"Model: {args.model}")
    print("=" * 60)

    text = read_text_file(input_file)
    chunks = chunk_text_with_llm(
        text=text,
        api_key=api_key,
        model=args.model,
        max_chunk_size=args.chunk_size,
        timeout=args.timeout,
    )

    print(f"\nSuccessfully created {len(chunks)} semantic chunks.")
    chunks_data = save_chunks(chunks, output_file)
    display_statistics(chunks_data)


if __name__ == "__main__":
    main()
