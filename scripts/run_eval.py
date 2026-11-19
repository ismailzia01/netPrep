#!/usr/bin/env python3
"""Evaluation runner for netPrep answer engines.

Validates subject eval/questions.json datasets and measures answer accuracy,
latency, and answer validity.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Ensure workspace root is in sys.path for direct script execution
workspace_root = Path(__file__).resolve().parent.parent
if str(workspace_root) not in sys.path:
    sys.path.insert(0, str(workspace_root))

from netprep.scan_pipeline import (
    AnswerEngine,
    DummyAnswerEngine,
    ParsedQuestion,
)
from netprep.subjects import SubjectPack, get_subject_pack, load_subject_pack


@dataclass
class EvalResult:
    """Detailed summary of an evaluation run."""

    subject_name: str
    engine_name: str
    total: int
    correct: int
    wrong: int
    invalid_count: int
    accuracy_pct: float
    avg_latency_ms: float
    total_time_sec: float
    wrong_questions: list[dict[str, Any]]


def validate_eval_questions(raw_data: Any) -> list[str]:
    """Validate question format per project specifications.

    Rules:
    - List of question objects
    - Unique 'id' across all items
    - 'question' is a non-empty string
    - 'options' contains exactly the keys 'A', 'B', 'C', 'D'
    - 'answer' is one of 'A', 'B', 'C', 'D'
    """
    errors: list[str] = []
    if not isinstance(raw_data, list):
        return ["Evaluation dataset must be a JSON array of question objects."]

    if len(raw_data) == 0:
        return ["Evaluation dataset is empty."]

    seen_ids: set[Any] = set()
    valid_keys = {"A", "B", "C", "D"}

    for idx, item in enumerate(raw_data):
        item_prefix = f"Question index {idx}"
        if not isinstance(item, dict):
            errors.append(f"{item_prefix}: item must be a JSON object.")
            continue

        q_id = item.get("id")
        if q_id is None:
            errors.append(f"{item_prefix}: missing required field 'id'.")
        elif q_id in seen_ids:
            errors.append(f"{item_prefix}: duplicate id '{q_id}'. IDs must be unique.")
        else:
            seen_ids.add(q_id)

        item_prefix = f"Question {q_id if q_id is not None else f'at index {idx}'}"

        q_text = item.get("question")
        if not isinstance(q_text, str) or not q_text.strip():
            errors.append(f"{item_prefix}: 'question' must be a non-empty string.")

        options = item.get("options")
        if not isinstance(options, dict):
            errors.append(f"{item_prefix}: 'options' must be a dictionary.")
        else:
            actual_keys = set(options.keys())
            if actual_keys != valid_keys:
                errors.append(
                    f"{item_prefix}: options keys must be exactly {sorted(valid_keys)}, "
                    f"got {sorted(actual_keys)}."
                )

        answer = item.get("answer")
        if not isinstance(answer, str) or answer.strip().upper() not in valid_keys:
            errors.append(
                f"{item_prefix}: 'answer' must be one of 'A', 'B', 'C', or 'D', got {repr(answer)}."
            )

    return errors


def resolve_engine(engine_name: str) -> AnswerEngine:
    """Instantiate an AnswerEngine based on name."""
    normalized = engine_name.strip().lower()
    if normalized in {"dummy", "stub"}:
        return DummyAnswerEngine(default_answer="B")
    raise ValueError(f"Unknown engine '{engine_name}'. Available engines: dummy")


def run_evaluation(
    questions: list[dict[str, Any]],
    engine: AnswerEngine,
    subject: SubjectPack | None = None,
    engine_name: str = "dummy",
) -> EvalResult:
    """Execute evaluation questions against an engine and collect statistics."""
    total = len(questions)
    correct = 0
    wrong = 0
    invalid_count = 0
    wrong_questions: list[dict[str, Any]] = []

    start_total_time = time.perf_counter()
    latencies: list[float] = []

    for item in questions:
        expected = str(item["answer"]).strip().upper()
        parsed = ParsedQuestion(
            question=item["question"],
            options=item["options"],
        )

        q_start = time.perf_counter()
        raw_pred = engine.answer(parsed, subject=subject)
        q_elapsed_ms = (time.perf_counter() - q_start) * 1000
        latencies.append(q_elapsed_ms)

        pred_cleaned = str(raw_pred).strip().upper()

        is_valid_letter = len(pred_cleaned) == 1 and pred_cleaned in {"A", "B", "C", "D"}
        if not is_valid_letter:
            invalid_count += 1
            wrong += 1
            wrong_questions.append(
                {
                    "id": item.get("id"),
                    "question": item.get("question", "")[:60],
                    "expected": expected,
                    "predicted": raw_pred,
                    "reason": "Invalid response format (not a single letter A-D)",
                }
            )
        elif pred_cleaned == expected:
            correct += 1
        else:
            wrong += 1
            wrong_questions.append(
                {
                    "id": item.get("id"),
                    "question": item.get("question", "")[:60],
                    "expected": expected,
                    "predicted": pred_cleaned,
                    "reason": "Mismatched answer",
                }
            )

    total_time_sec = time.perf_counter() - start_total_time
    avg_latency_ms = sum(latencies) / total if total > 0 else 0.0
    accuracy_pct = (correct / total) * 100.0 if total > 0 else 0.0

    return EvalResult(
        subject_name=subject.name if subject else "General",
        engine_name=engine_name,
        total=total,
        correct=correct,
        wrong=wrong,
        invalid_count=invalid_count,
        accuracy_pct=accuracy_pct,
        avg_latency_ms=avg_latency_ms,
        total_time_sec=total_time_sec,
        wrong_questions=wrong_questions,
    )


def print_report(res: EvalResult) -> None:
    """Print a clean CLI summary report."""
    border = "=" * 65
    print("\n" + border)
    print(f" netPrep Evaluation Report: {res.subject_name}")
    print(f" Engine: {res.engine_name}")
    print(border)
    print(f" Total Questions      : {res.total}")
    print(f" Correct Answers      : {res.correct}")
    print(f" Wrong Answers        : {res.wrong}")
    print(f" Invalid Answers      : {res.invalid_count} (no letter or multiple letters)")
    print(f" Overall Accuracy     : {res.accuracy_pct:.1f}% ({res.correct}/{res.total})")
    print(f" Average Time/Question: {res.avg_latency_ms:.2f} ms")
    print(f" Total Evaluation Time: {res.total_time_sec:.3f} s")
    print(border)

    if res.wrong_questions:
        print("\nIncorrect / Invalid Questions:")
        for idx, wq in enumerate(res.wrong_questions, start=1):
            q_id = wq["id"]
            snippet = wq["question"]
            exp = wq["expected"]
            pred = wq["predicted"]
            reason = wq["reason"]
            print(f" {idx}. [ID {q_id}] \"{snippet}...\"")
            print(f"    Expected: {exp} | Predicted: {pred} ({reason})")
    else:
        print("\nAll questions answered correctly! 100% Accuracy.")
    print(border + "\n")


def main() -> None:
    """Parse CLI options, validate dataset, run evaluation, and output results."""
    parser = argparse.ArgumentParser(
        description="Run evaluation on netPrep multiple-choice question datasets."
    )
    parser.add_argument(
        "--subject",
        default="computer_networks",
        help="Subject pack identifier or folder name in subjects/ (default: computer_networks)",
    )
    parser.add_argument(
        "--engine",
        default="dummy",
        help="AnswerEngine implementation to test (default: dummy)",
    )
    parser.add_argument(
        "--eval-file",
        default=None,
        help="Custom path to an eval questions.json file",
    )
    args = parser.parse_args()

    # Locate subject pack and eval file
    subjects_dir = workspace_root / "subjects"
    subject = get_subject_pack(args.subject, subjects_dir)

    if args.eval_file:
        eval_path = Path(args.eval_file).resolve()
    elif subject is not None and subject.eval_file.exists():
        eval_path = subject.eval_file
    else:
        eval_path = subjects_dir / args.subject / "eval" / "questions.json"

    if not eval_path.exists():
        sys.stderr.write(f"Error: Evaluation file not found at: {eval_path}\n")
        sys.exit(1)

    try:
        content = json.loads(eval_path.read_text(encoding="utf-8"))
    except Exception as exc:
        sys.stderr.write(f"Error reading JSON from {eval_path}: {exc}\n")
        sys.exit(1)

    # Validate dataset format
    validation_errors = validate_eval_questions(content)
    if validation_errors:
        sys.stderr.write(f"Dataset Validation Failed for {eval_path}:\n")
        for err in validation_errors:
            sys.stderr.write(f"  - {err}\n")
        sys.exit(1)

    try:
        engine = resolve_engine(args.engine)
    except ValueError as exc:
        sys.stderr.write(f"Error: {exc}\n")
        sys.exit(1)

    result = run_evaluation(content, engine=engine, subject=subject, engine_name=args.engine)
    print_report(result)


if __name__ == "__main__":
    main()
