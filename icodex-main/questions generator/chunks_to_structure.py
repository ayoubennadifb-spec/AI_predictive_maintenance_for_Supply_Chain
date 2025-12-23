"""
Build a hierarchical course structure JSON from chunked text using the Cerebras Chat Completions API.

Pipeline role:
  - Reads <*_chunks.json> produced by text_to_chunks.Py
  - Produces a structured JSON with hierarchy:
      course -> modules -> mini_modules -> concepts -> mini_concepts
  - Each mini_concept includes grounding evidence excerpts to reduce out-of-context questions.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

import requests

CEREBRAS_API_ENDPOINT = "https://api.cerebras.ai/v1/"


def read_chunks_from_file(file_path: str) -> list[dict[str, Any]]:
    """Read chunks from a JSON file."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        chunks = data.get("chunks")
        if not isinstance(chunks, list):
            raise KeyError("chunks")
        return chunks
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found.")
        sys.exit(1)
    except (KeyError, json.JSONDecodeError) as exc:
        print(f"Error reading chunks from file: {exc}")
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
    start_index = content.find("{")
    end_index = content.rfind("}")
    if start_index != -1 and end_index != -1 and end_index > start_index:
        return content[start_index : end_index + 1]
    return content


def structure_chunks_with_llm(
    chunks: list[dict[str, Any]],
    api_key: str,
    model: str = "llama3.1-8b",
    timeout: int = 300,
    target_mini_concepts: int = 100,
    max_mini_concepts: int = 120,
) -> Dict[str, Any]:
    print("Structuring chunks with LLM...")

    target_mini_concepts = max(1, int(target_mini_concepts or 1))
    max_mini_concepts = max(target_mini_concepts, int(max_mini_concepts or target_mini_concepts))

    text_content = "\n\n".join([str(chunk.get("text", "")) for chunk in chunks])
    text_content = "\n".join(
        line for line in text_content.splitlines() if line.strip().lower() not in {"none", "null"}
    )

    prompt = f"""You are a deterministic CONTENT-STRUCTURING engine.

Task: analyze the INPUT TEXT and output ONE hierarchical JSON object representing the course structure.

ABSOLUTE OUTPUT RULES:
1) Output ONLY a single valid JSON object inside ONE markdown code block exactly like:
```json
{{ ... }}
```
2) Do NOT output any text before or after the JSON block.
3) The JSON must be strictly valid:
   - Use double quotes for all keys and string values
   - No trailing commas
   - No comments
   - No duplicate keys
4) Do NOT invent content that is not supported by the input text.

LANGUAGE RULES (CRITICAL):
- Detect the dominant language of the input text (e.g., Spanish/French/English).
- Write ALL generated strings (titles, summaries, keywords) in that same language.
- Do NOT translate the input. Evidence excerpts must be verbatim from the input text.

REQUIRED HIERARCHY (MUST MATCH EXACTLY):
course -> modules -> mini_modules -> concepts -> mini_concepts

SCHEMA (MUST MATCH):
{{
  "course": {{
    "title": "string",
    "description": "string",
    "modules": [
      {{
        "title": "string",
        "summary": "string",
        "mini_modules": [
          {{
            "title": "string",
            "summary": "string",
            "concepts": [
              {{
                "title": "string",
                "summary": "string",
                "mini_concepts": [
                  {{
                    "title": "string",
                    "summary": "string",
                    "keywords": ["string"],
                    "source_evidence": ["string"]
                  }}
                ]
              }}
            ]
          }}
        ]
      }}
    ]
  }}
}}

SEMANTIC RULES:
- Modules represent major themes or chapters.
- Mini-modules represent subtopics within a module.
- Concepts represent teachable ideas (definitions, rules, methods).
- Mini-concepts are the smallest assessable units: ONE idea each, suitable for ONE high-quality multiple-choice question.
- Mini-concepts should be phrased as specific, testable claims (something a student could get right/wrong), not just topic labels.
- Preserve the logical order of topics as they appear in the input.
- Do NOT skip major sections; if needed, group loosely related content instead of omitting it.
- Do NOT create mini_concepts that are purely document-structure (e.g., table of contents, acknowledgements, references).

ASSESSMENT FOCUS (CRITICAL):
- If the input is a technical course (programming, math, engineering, sciences), prioritize technical/operational content:
  syntax/semantics, rules, constraints, edge cases, algorithms, step-by-step procedures, common pitfalls, error conditions.
- De-prioritize (or omit) non-technical "general knowledge" content like history/origin, biographies, popularity, marketing,
  and motivational content unless it is a major graded learning objective in the text.
- For programming courses specifically, prefer mini-concepts about code behavior (e.g., loops, functions, data structures)
  rather than "What is X?" at a generic level.

TITLE & SUMMARY RULES:
- Titles must be short, clear, and specific (2-8 words).
- Prefer headings or repeated terms from the text when available.
- Summaries must be concise (1-2 sentences), faithful to the text, and information-dense.
- When available in the text, include key conditions/constraints (e.g., when/if/only) and the main consequence/purpose.
- Do NOT add opinions, marketing language, or external explanations.
- Avoid placeholder/generic titles like "Empty Course" unless the input text explicitly contains that phrase.

KEYWORDS RULES:
- Each mini_concept must contain 3-8 keywords.
- Keywords should be important terms appearing in the input text.
- Prefer domain-specific terms, variable names, symbols, and exact phrases used in the text.
- Avoid vague keywords (e.g., "overview", "introduction", "concept").
- Each keyword should appear in at least one evidence excerpt for that mini_concept.

SOURCE EVIDENCE RULES (CRITICAL):
- Each mini_concept must include 1-3 short verbatim excerpts from the input text.
- Each excerpt must be <= 20 words.
- Excerpts must be copied exactly from the input text (no rewriting).
- Evidence must clearly justify the mini_concept (definition/rule/constraint/step) rather than only a vague mention.

SIZE / SPEED TARGET:
- Aim for about {target_mini_concepts} total mini_concepts across the whole output.
- Do NOT exceed {max_mini_concepts} total mini_concepts.
- Prefer merging duplicates/noise and focusing on high-yield, testable ideas.
- If the text is short, output fewer elements while keeping the full hierarchy.

PDF / OCR NOISE HANDLING:
- The input may contain page numbers, headers/footers, broken lines, or duplicated fragments.
- Ignore obvious noise when inferring structure.
- If content is duplicated, merge it into a single concept rather than repeating it.
- Ignore synthetic markers like "--- Page N ---" when they appear.

FINAL VALIDATION (SILENT):
- JSON is valid and parsable
- All hierarchy levels and required fields exist
- Every mini_concept contains: title, summary, keywords, source_evidence
- Exactly ONE ```json code block is output

INPUT TEXT:
{text_content}
"""

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
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
        content = data["choices"][0]["message"]["content"].strip()
        json_content = _extract_json_block(content)

        try:
            structure = json.loads(json_content)
        except json.JSONDecodeError as exc:
            print("Error decoding model response as JSON:")
            print("Extracted content to parse:")
            print(json_content)
            print("\nJSON error:", str(exc))
            sys.exit(1)

        return structure
    except requests.exceptions.RequestException as exc:
        print(f"Network error: {exc}")
        sys.exit(1)
    except Exception as exc:
        print(f"Unexpected error: {exc}")
        sys.exit(1)


def save_structure(structure: Dict[str, Any], output_path: str) -> None:
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(structure, f, indent=2, ensure_ascii=False)
        print(f"\nStructure saved to: {output_path}")
    except Exception as exc:
        print(f"Error saving file: {exc}")
        sys.exit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Structure text chunks using Cerebras LLM.")
    parser.add_argument("-i", "--input", default="hibernate_extracted_chunks.json")
    parser.add_argument("-o", "--output")
    parser.add_argument("-m", "--model", default="llama3.1-8b")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument(
        "--target-mini-concepts",
        type=int,
        default=100,
        help="Target total mini_concepts for the whole course (default: 100).",
    )
    parser.add_argument(
        "--max-mini-concepts",
        type=int,
        default=120,
        help="Hard cap for total mini_concepts (default: 120).",
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
    output_file = args.output or (Path(input_file).stem + "_structure.json")

    print("Chunk Structuring (Cerebras Edition)")
    print("=" * 60)
    print(f"Input file: {input_file}")
    print(f"Output file: {output_file}")
    print(f"Model: {args.model}")
    print(f"Target mini_concepts: {args.target_mini_concepts} (max {args.max_mini_concepts})")
    print("=" * 60)

    chunks = read_chunks_from_file(input_file)
    structure = structure_chunks_with_llm(
        chunks=chunks,
        api_key=api_key,
        model=args.model,
        timeout=args.timeout,
        target_mini_concepts=args.target_mini_concepts,
        max_mini_concepts=args.max_mini_concepts,
    )
    save_structure(structure, output_file)
    print("\nStructuring complete.")


if __name__ == "__main__":
    main()
