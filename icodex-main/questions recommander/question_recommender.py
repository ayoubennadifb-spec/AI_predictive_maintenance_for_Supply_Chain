"""
Recommend the next question to ask based on prior performance.

Inputs:
- A quiz JSON (same format produced by the question generator).
- An evaluation JSON from answer_evaluator.py.
- Optionally a mastery JSON from mastery_scorer.py or a manual score.
Outputs a JSON object with the chosen question, its position, reason, and score used.
"""

import argparse
import json
import re
from typing import Any, Dict, List, Optional, Tuple


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def question_key(question: Dict[str, Any]) -> str:
    value = question.get("id") or question.get("question") or ""
    return str(value).strip()


def normalize_question_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip().lower()
    cleaned = re.sub(r"[^\w\s]", "", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def question_signature(question: Dict[str, Any]) -> str:
    if not isinstance(question, dict):
        return ""
    for key in ("question", "prompt", "text"):
        value = question.get(key)
        if isinstance(value, str) and value.strip():
            return normalize_question_text(value)
    fallback = question_key(question)
    return normalize_question_text(fallback)


def should_add_signature(value: str) -> bool:
    return bool(re.search(r"\s", value)) or "?" in value


def normalize_position(position: str) -> str:
    return "/".join([seg for seg in position.replace("\\", "/").split("/") if seg])


def find_node_by_position(
    root: Dict[str, Any], target_position: str
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Walk the quiz tree to find the node whose path matches target_position.
    Returns (node, trace). Trace keeps ordered segments with node references.
    """
    target = normalize_position(target_position)

    def walk(node: Any, segments: List[str], trace: List[Dict[str, Any]]):
        # Match before stepping deeper
        if "/".join(segments) == target:
            return node, trace

        if isinstance(node, dict):
            seg_with_title = segments
            trace_with_title = trace

            if node.get("title"):
                seg_with_title = segments + [node["title"]]
                trace_with_title = trace + [
                    {"type": "title", "value": node["title"], "node": node}
                ]
                if "/".join(seg_with_title) == target:
                    return node, trace_with_title

            for key, value in node.items():
                if key in {"title", "questions"}:
                    continue
                child_segments = seg_with_title + [key]
                child_trace = trace_with_title + [
                    {"type": "key", "value": key, "node": node}
                ]
                found = walk(value, child_segments, child_trace)
                if found:
                    return found

        elif isinstance(node, list):
            for item in node:
                found = walk(item, segments, trace)
                if found:
                    return found

        return None

    for key, value in root.items():
        initial_segments = [key]
        initial_trace = [{"type": "key", "value": key, "node": root}]
        result = walk(value, initial_segments, initial_trace)
        if result:
            return result

    return None, []


def position_for_node(root: Dict[str, Any], target: Dict[str, Any]) -> str:
    def walk(node: Any, segments: List[str]) -> Optional[List[str]]:
        seg_with_title = segments
        if isinstance(node, dict):
            if node.get("title"):
                seg_with_title = segments + [node["title"]]
                if node is target:
                    return seg_with_title
            elif node is target:
                return seg_with_title

            for key, value in node.items():
                if key in {"title", "questions"}:
                    continue
                result = walk(value, seg_with_title + [key])
                if result:
                    return result

        elif isinstance(node, list):
            for item in node:
                result = walk(item, segments)
                if result:
                    return result

        return None

    for key, value in root.items():
        result = walk(value, [key])
        if result:
            return "/".join([seg for seg in result if seg])

    return ""


def derive_context(trace: List[Dict[str, Any]]) -> Dict[str, Any]:
    ctx: Dict[str, Any] = {
        "course_node": None,
        "module_node": None,
        "module_parent": None,
        "mini_module_node": None,
        "mini_module_parent": None,
    }

    for idx, entry in enumerate(trace):
        if entry["type"] == "key":
            if entry["value"] == "course" and idx + 1 < len(trace):
                nxt = trace[idx + 1]
                if nxt["type"] == "title":
                    ctx["course_node"] = nxt["node"]
            if entry["value"] == "modules" and idx + 1 < len(trace):
                nxt = trace[idx + 1]
                if nxt["type"] == "title":
                    ctx["module_node"] = nxt["node"]
                    ctx["module_parent"] = entry["node"]
            if entry["value"] == "mini_modules" and idx + 1 < len(trace):
                nxt = trace[idx + 1]
                if nxt["type"] == "title":
                    ctx["mini_module_node"] = nxt["node"]
                    ctx["mini_module_parent"] = entry["node"]
    return ctx


def performance_score(
    evaluation: Dict[str, Any],
    mastery: Optional[Dict[str, Any]],
    override_score: Optional[float],
) -> float:
    if override_score is not None:
        return float(override_score)

    if mastery and isinstance(mastery.get("mastery_score"), (int, float)):
        return float(mastery["mastery_score"])

    metrics = evaluation.get("metrics", {})
    accuracy = float(metrics.get("normalized_accuracy", 0.0) or 0.0)
    speed = float(metrics.get("speed_score", 0.0) or 0.0)
    confidence = float(metrics.get("confidence", 0.0) or 0.0)
    difficulty = float(metrics.get("difficulty_weight", 1.0) or 1.0)
    base = (0.6 * accuracy + 0.25 * speed + 0.15 * confidence) * 100
    return base * difficulty


def choose_question_from_node(
    node: Optional[Dict[str, Any]],
    exclude_questions: set[str],
    exclude_signatures: set[str],
) -> Optional[Dict[str, Any]]:
    if not isinstance(node, dict):
        return None
    for q in node.get("questions", []):
        qk = question_key(q) if isinstance(q, dict) else ""
        qsig = question_signature(q) if isinstance(q, dict) else ""
        if qk and qk in exclude_questions:
            continue
        if qsig and qsig in exclude_signatures:
            continue
        if qk or qsig:
            return q
    return None


def sibling_nodes(
    parent: Optional[Dict[str, Any]], key: str, exclude_node: Optional[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    if not isinstance(parent, dict) or key not in parent:
        return []

    raw = parent[key]
    nodes: List[Dict[str, Any]] = []

    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and item is not exclude_node:
                nodes.append(item)
    elif isinstance(raw, dict):
        if raw is not exclude_node:
            nodes.append(raw)

    return nodes


def first_question_anywhere(
    root: Dict[str, Any],
    exclude_questions: set[str],
    exclude_signatures: set[str],
) -> Optional[Tuple[Dict[str, Any], Dict[str, Any]]]:
    stack: List[Any] = [root]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for q in node.get("questions", []):
                qk = question_key(q) if isinstance(q, dict) else ""
                qsig = question_signature(q) if isinstance(q, dict) else ""
                if qk and qk in exclude_questions:
                    continue
                if qsig and qsig in exclude_signatures:
                    continue
                if qk or qsig:
                    return node, q
            for value in node.values():
                if isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(node, list):
            for item in node:
                stack.append(item)
    return None


def build_signature_index(root: Dict[str, Any]) -> Dict[str, str]:
    index: Dict[str, str] = {}
    stack: List[Any] = [root]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for q in node.get("questions", []):
                if not isinstance(q, dict):
                    continue
                qid = str(q.get("id") or "").strip()
                qsig = question_signature(q)
                if qid and qsig:
                    index[qid] = qsig
            for value in node.values():
                if isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(node, list):
            stack.extend(node)
    return index


def recommend_question(
    quiz: Dict[str, Any],
    evaluation: Dict[str, Any],
    mastery: Optional[Dict[str, Any]],
    override_score: Optional[float],
    exclude_questions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    position = normalize_position(evaluation.get("position", ""))
    current_question_id = evaluation.get("question_id") or evaluation.get("questionId") or ""
    current_question = evaluation.get("question", "")
    exclude_set: set[str] = set()
    exclude_signatures: set[str] = set()
    for value in exclude_questions or []:
        if isinstance(value, str) and value.strip():
            cleaned = value.strip()
            exclude_set.add(cleaned)
            if should_add_signature(cleaned):
                signature = normalize_question_text(cleaned)
                if signature:
                    exclude_signatures.add(signature)
    if isinstance(current_question_id, str) and current_question_id.strip():
        exclude_set.add(current_question_id.strip())
    if isinstance(current_question, str) and current_question.strip():
        signature = normalize_question_text(current_question)
        if signature:
            exclude_signatures.add(signature)
    signature_index = build_signature_index(quiz)
    for value in list(exclude_set):
        signature = signature_index.get(value)
        if signature:
            exclude_signatures.add(signature)
    target_node, trace = find_node_by_position(quiz, position)
    ctx = derive_context(trace)

    score = performance_score(evaluation, mastery, override_score)
    low_cut, mid_cut = 50.0, 75.0
    reason = ""
    selected_question: Optional[Dict[str, Any]] = None
    source_node: Optional[Dict[str, Any]] = None

    def pick_from_nodes(nodes_with_reason: List[Tuple[str, Optional[Dict[str, Any]]]]):
        nonlocal selected_question, source_node, reason
        for r, node in nodes_with_reason:
            q = choose_question_from_node(node, exclude_set, exclude_signatures)
            if q:
                selected_question = q
                source_node = node
                reason = r
                return True
        return False

    if score < low_cut:
        pick_from_nodes(
            [
                ("reinforce_same_node", target_node),
                ("reinforce_mini_module", ctx.get("mini_module_node")),
                ("check_module_level", ctx.get("module_node")),
            ]
        )
        if not selected_question and ctx.get("mini_module_parent") and ctx.get(
            "mini_module_node"
        ):
            for node in sibling_nodes(
                ctx["mini_module_parent"], "mini_modules", ctx["mini_module_node"]
            ):
                q = choose_question_from_node(node, exclude_set, exclude_signatures)
                if q:
                    selected_question = q
                    source_node = node
                    reason = "probe_other_mini_modules_in_module"
                    break

    elif score < mid_cut:
        if ctx.get("mini_module_parent") and ctx.get("mini_module_node"):
            for node in sibling_nodes(
                ctx["mini_module_parent"], "mini_modules", ctx["mini_module_node"]
            ):
                q = choose_question_from_node(node, exclude_set, exclude_signatures)
                if q:
                    selected_question = q
                    source_node = node
                    reason = "cover_other_mini_modules_in_module"
                    break
        if not selected_question:
            pick_from_nodes(
                [
                    ("check_module_level", ctx.get("module_node")),
                    ("reinforce_same_node", target_node),
                ]
            )

    else:
        if ctx.get("module_parent") and ctx.get("module_node"):
            for node in sibling_nodes(
                ctx["module_parent"], "modules", ctx["module_node"]
            ):
                q = choose_question_from_node(node, exclude_set, exclude_signatures)
                if q:
                    selected_question = q
                    source_node = node
                    reason = "advance_to_other_module"
                    break
        if not selected_question and ctx.get("mini_module_parent") and ctx.get(
            "mini_module_node"
        ):
            for node in sibling_nodes(
                ctx["mini_module_parent"], "mini_modules", ctx["mini_module_node"]
            ):
                q = choose_question_from_node(node, exclude_set, exclude_signatures)
                if q:
                    selected_question = q
                    source_node = node
                    reason = "sample_other_mini_modules"
                    break
        if not selected_question:
            pick_from_nodes(
                [
                    ("stretch_module_level", ctx.get("module_node")),
                    ("broaden_course_level", ctx.get("course_node")),
                ]
            )

    if not selected_question:
        anywhere = first_question_anywhere(quiz, exclude_set, exclude_signatures)
        if anywhere:
            source_node, selected_question = anywhere
            reason = "fallback_first_available"

    if not selected_question:
        return {
            "error": "No available question found",
            "performance_score": round(score, 2),
        }

    position_out = position_for_node(quiz, source_node) if source_node else ""

    return {
        "selected_question": selected_question,
        "position": position_out,
        "reason": reason,
        "performance_score": round(score, 2),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Recommend the next quiz question based on prior performance.",
    )
    parser.add_argument(
        "--quiz",
        default="questions generator/python-cheatsheet_extracted_chunks_structure_quiz.json",
        help="Path to quiz JSON with questions.",
    )
    parser.add_argument(
        "--evaluation",
        required=True,
        help="Evaluation JSON from answer_evaluator.py.",
    )
    parser.add_argument(
        "--mastery",
        help="Optional mastery JSON from mastery_scorer.py.",
    )
    parser.add_argument(
        "--score",
        type=float,
        help="Optional manual performance score to override other inputs.",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indentation for output.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    quiz = load_json(args.quiz)
    evaluation = load_json(args.evaluation)
    mastery = load_json(args.mastery) if args.mastery else None

    recommendation = recommend_question(
        quiz=quiz,
        evaluation=evaluation,
        mastery=mastery,
        override_score=args.score,
    )
    print(json.dumps(recommendation, indent=args.indent, ensure_ascii=False))


if __name__ == "__main__":
    main()
