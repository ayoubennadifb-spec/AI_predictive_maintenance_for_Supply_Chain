"""
Evaluate a single student answer and emit performance parameters.
"""

import argparse
import json
from difflib import SequenceMatcher
from typing import Dict, Any


DIFFICULTY_WEIGHTS = {
    "easy": 0.9,
    "medium": 1.0,
    "hard": 1.15,
    "very_hard": 1.3,
}


def clamp(value: float, min_value: float = 0.0, max_value: float = 1.0) -> float:
    return max(min_value, min(max_value, value))


def normalize_text(value: str) -> str:
    return " ".join(value.strip().lower().split())


def similarity_score(correct_answer: str, student_answer: str) -> float:
    if not correct_answer or not student_answer:
        return 0.0
    matcher = SequenceMatcher(None, normalize_text(correct_answer), normalize_text(student_answer))
    return clamp(matcher.ratio())


def compute_confidence(normalized_accuracy: float, speed_score: float, timing_alignment: float) -> float:
    weighted = 0.6 * normalized_accuracy + 0.25 * speed_score + 0.15 * timing_alignment
    return clamp(weighted)


def evaluate_answer(
    question: str,
    correct_answer: str,
    student_answer: str,
    time_taken: float,
    expected_time: float,
    difficulty: str,
    position: str,
) -> Dict[str, Any]:
    difficulty_key = normalize_text(difficulty or "medium")
    difficulty_weight = DIFFICULTY_WEIGHTS.get(difficulty_key, DIFFICULTY_WEIGHTS["medium"])

    normalized_correct = normalize_text(correct_answer)
    normalized_student = normalize_text(student_answer)
    is_correct = normalized_correct == normalized_student

    similarity = similarity_score(correct_answer, student_answer)
    normalized_accuracy = 1.0 if is_correct else similarity

    safe_expected_time = expected_time if expected_time > 0 else 1.0
    time_ratio = time_taken / safe_expected_time

    if time_ratio <= 1.0:
        speed_score = clamp(1.0 - (1.0 - time_ratio) * 0.25)
    else:
        speed_score = clamp(1.0 - (time_ratio - 1.0) * 0.7)

    timing_alignment = clamp(1.0 - abs(time_ratio - 1.0) * 0.6)
    confidence = compute_confidence(normalized_accuracy, speed_score, timing_alignment)

    pacing_flag = (
        "fast" if time_ratio < 0.8 else "on_time" if time_ratio <= 1.2 else "slow"
    )

    parameters = {
        "question": question,
        "position": position,
        "difficulty": difficulty_key,
        "correct_answer": correct_answer,
        "student_answer": student_answer,
        "time_taken_seconds": round(time_taken, 3),
        "expected_time_seconds": round(safe_expected_time, 3),
        "metrics": {
            "is_correct": is_correct,
            "text_similarity": round(similarity, 3),
            "normalized_accuracy": round(normalized_accuracy, 3),
            "time_ratio": round(time_ratio, 3),
            "speed_score": round(speed_score, 3),
            "timing_alignment": round(timing_alignment, 3),
            "difficulty_weight": round(difficulty_weight, 3),
            "confidence": round(confidence, 3),
        },
        "notes": {
            "pacing": pacing_flag,
        },
    }

    return parameters


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate a student answer and compute performance parameters.",
    )
    parser.add_argument(
        "--question",
        default="What is the purpose of the `__name__` variable in Python?",
        help="The question text.",
    )
    parser.add_argument(
        "--correct-answer",
        default="It is used to determine the current module name.",
        help="Expected correct answer.",
    )
    parser.add_argument(
        "--student-answer",
        default="It indicates whether the module is run directly or imported by exposing the module name",
        help="Student's submitted answer.",
    )
    parser.add_argument(
        "--time-taken",
        type=float,
        default=18.0,
        help="Time the student took to answer (in seconds).",
    )
    parser.add_argument(
        "--expected-time",
        type=float,
        default=20.0,
        help="Target time for the question (in seconds).",
    )
    parser.add_argument(
        "--difficulty",
        default="medium",  # change if you want a different default
        help="Difficulty label (easy, medium, hard, very_hard).",
    )
    parser.add_argument(
        "--position",
        default="course/Real Python Pocket Reference",
        help="Question position in the structure, e.g. course/module/concept.",
    )
    parser.add_argument(
        "--output",
        help="Optional path to write the evaluation JSON. Prints to stdout when omitted.",
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
    evaluation = evaluate_answer(
        question=args.question,
        correct_answer=args.correct_answer,
        student_answer=args.student_answer,
        time_taken=args.time_taken,
        expected_time=args.expected_time,
        difficulty=args.difficulty,
        position=args.position,
    )

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(evaluation, f, indent=args.indent, ensure_ascii=False)
    else:
        print(json.dumps(evaluation, indent=args.indent, ensure_ascii=False))


if __name__ == "__main__":
    main()
