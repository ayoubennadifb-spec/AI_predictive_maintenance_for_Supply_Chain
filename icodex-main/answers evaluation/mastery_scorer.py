"""
Compute a mastery score out of 100 from evaluation parameters.
"""

import argparse
import json
import sys
from typing import Any, Dict


def clamp(value: float, min_value: float = 0.0, max_value: float = 100.0) -> float:
    return max(min_value, min(max_value, value))


def load_evaluation(source: str) -> Dict[str, Any]:
    if source == "-":
        return json.load(sys.stdin)
    with open(source, "r", encoding="utf-8") as f:
        return json.load(f)


def calculate_mastery(evaluation: Dict[str, Any]) -> Dict[str, Any]:
    metrics = evaluation.get("metrics", {})

    accuracy = float(metrics.get("normalized_accuracy", 0.0) or 0.0)
    speed_score = float(metrics.get("speed_score", 0.0) or 0.0)
    confidence = float(metrics.get("confidence", 0.0) or 0.0)
    difficulty_weight = float(metrics.get("difficulty_weight", 1.0) or 1.0)
    time_ratio = float(metrics.get("time_ratio", 1.0) or 1.0)
    is_correct = bool(metrics.get("is_correct", False))

    base_score = (0.6 * accuracy + 0.25 * speed_score + 0.15 * confidence) * 100
    difficulty_adjusted = base_score * difficulty_weight
    correctness_bonus = 3.0 if is_correct else 0.0

    pacing_penalty = 0.0
    if time_ratio > 1.4:
        pacing_penalty = (time_ratio - 1.4) * 15

    mastery_score = clamp(difficulty_adjusted + correctness_bonus - pacing_penalty)

    return {
        "question": evaluation.get("question", ""),
        "position": evaluation.get("position", ""),
        "difficulty": evaluation.get("difficulty", ""),
        "mastery_score": round(mastery_score, 1),
        "components": {
            "base_score": round(base_score, 2),
            "difficulty_weight": round(difficulty_weight, 3),
            "difficulty_adjusted": round(difficulty_adjusted, 2),
            "correctness_bonus": round(correctness_bonus, 2),
            "pacing_penalty": round(pacing_penalty, 2),
            "normalized_accuracy": round(accuracy, 3),
            "speed_score": round(speed_score, 3),
            "confidence": round(confidence, 3),
            "time_ratio": round(time_ratio, 3),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute a mastery score out of 100 for a single evaluated question.",
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to the evaluation JSON produced by answer_evaluator.py (use '-' for stdin).",
    )
    parser.add_argument(
        "--output",
        help="Optional path to write the mastery JSON. Prints to stdout when omitted.",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indentation for pretty output.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    evaluation = load_evaluation(args.input)
    mastery = calculate_mastery(evaluation)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(mastery, f, indent=args.indent, ensure_ascii=False)
    else:
        print(json.dumps(mastery, indent=args.indent, ensure_ascii=False))


if __name__ == "__main__":
    main()
