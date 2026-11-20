#!/usr/bin/env python3
"""Evaluation runner for netPrep answer engines.

Validates subject eval/questions.json datasets and measures answer accuracy,
latency percentiles (avg, p50, p95), predicted letter distributions,
topic breakdown, and side-by-side model comparisons.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Ensure workspace root is in sys.path for direct script execution
workspace_root = Path(__file__).resolve().parent.parent
if str(workspace_root) not in sys.path:
    sys.path.insert(0, str(workspace_root))

from netprep.answer_engine import (
    INVALID_ANSWER,
    OllamaAnswerEngine,
    OllamaConnectionError,
    OllamaModelNotFoundError,
    OllamaTimeoutError,
)
from netprep.scan_pipeline import (
    AnswerEngine,
    DummyAnswerEngine,
    ParsedQuestion,
)
from netprep.subjects import SubjectPack, get_subject_pack


@dataclass
class EvalResult:
    """Detailed summary of an evaluation run."""

    subject_name: str
    engine_name: str
    model_name: str
    total: int
    correct: int
    wrong: int
    invalid_count: int
    accuracy_pct: float
    avg_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    total_time_sec: float
    predicted_distribution: dict[str, int]
    topic_accuracy: dict[str, dict[str, Any]] = field(default_factory=dict)
    split: str | None = None
    balance_warning: str | None = None
    wrong_questions: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert result to serializable dictionary."""
        return asdict(self)


def compute_latencies(latencies: list[float]) -> tuple[float, float, float]:
    """Compute average, p50 (median), and p95 latency in milliseconds."""
    if not latencies:
        return 0.0, 0.0, 0.0
    sorted_l = sorted(latencies)
    n = len(sorted_l)
    avg = sum(sorted_l) / n

    # Median (p50)
    if n % 2 == 1:
        p50 = sorted_l[n // 2]
    else:
        p50 = (sorted_l[n // 2 - 1] + sorted_l[n // 2]) / 2.0

    # p95 (95th percentile)
    idx95 = max(0, min(n - 1, int(round(0.95 * (n - 1)))))
    p95 = sorted_l[idx95]
    return avg, p50, p95


def check_dataset_balance(questions: list[dict[str, Any]]) -> tuple[dict[str, int], str | None]:
    """Check distribution of ground-truth answers in the dataset.

    Returns the letter count dict and an optional warning string if any letter > 50%.
    """
    counts = {"A": 0, "B": 0, "C": 0, "D": 0}
    total = len(questions)
    for q in questions:
        ans = str(q.get("answer", "")).strip().upper()
        if ans in counts:
            counts[ans] += 1

    warning: str | None = None
    if total > 0:
        for letter, count in counts.items():
            pct = (count / total) * 100.0
            if pct > 50.0 and total >= 2:
                warning = (
                    f"Dataset answer distribution is unbalanced! Option '{letter}' represents "
                    f"{pct:.1f}% of answers ({count}/{total}). Ground-truth counts: "
                    + ", ".join(f"{k}: {v}" for k, v in counts.items())
                )
                break
    return counts, warning


def validate_eval_questions(raw_data: Any) -> list[str]:
    """Validate question format per project specifications.

    Rules:
    - List of question objects
    - Unique 'id' across all items
    - 'question' is a non-empty string
    - 'options' contains exactly the keys 'A', 'B', 'C', 'D'
    - 'answer' is one of 'A', 'B', 'C', 'D'
    - Optional 'split' must be 'dev' or 'holdout' if present
    - Optional 'topic' must be a non-empty string if present
    """
    errors: list[str] = []
    if not isinstance(raw_data, list):
        return ["Evaluation dataset must be a JSON array of question objects."]

    if len(raw_data) == 0:
        return ["Evaluation dataset is empty."]

    seen_ids: set[Any] = set()
    valid_keys = {"A", "B", "C", "D"}
    valid_splits = {"dev", "holdout"}

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

        split_val = item.get("split")
        if split_val is not None and split_val not in valid_splits:
            errors.append(
                f"{item_prefix}: 'split' must be 'dev' or 'holdout', got {repr(split_val)}."
            )

        topic_val = item.get("topic")
        if topic_val is not None and (not isinstance(topic_val, str) or not topic_val.strip()):
            errors.append(f"{item_prefix}: 'topic' must be a non-empty string if provided.")

    return errors


def resolve_engine(engine_name: str, model_name: str | None = None) -> AnswerEngine:
    """Instantiate an AnswerEngine based on name and model."""
    normalized = engine_name.strip().lower()
    if normalized in {"dummy", "stub"}:
        return DummyAnswerEngine(default_answer="B")
    if normalized == "ollama":
        target_model = model_name or "qwen2.5:1.5b"
        return OllamaAnswerEngine(model_name=target_model)
    raise ValueError(f"Unknown engine '{engine_name}'. Available engines: dummy, ollama")


def run_evaluation(
    questions: list[dict[str, Any]],
    engine: AnswerEngine,
    subject: SubjectPack | None = None,
    engine_name: str = "dummy",
    model_name: str = "dummy",
    split: str | None = None,
) -> EvalResult:
    """Execute evaluation questions against an engine and collect comprehensive statistics."""
    # Filter by split if requested
    if split:
        filtered = [q for q in questions if q.get("split") == split]
        if not filtered:
            sys.stderr.write(f"Warning: No questions match split '{split}'.\n")
        eval_questions = filtered
    else:
        eval_questions = questions

    total = len(eval_questions)
    correct = 0
    wrong = 0
    invalid_count = 0
    wrong_questions: list[dict[str, Any]] = []

    # Letter distribution counts
    pred_distribution = {"A": 0, "B": 0, "C": 0, "D": 0, "INVALID": 0}

    # Per-topic accuracy tracking: topic -> {total, correct}
    topic_stats: dict[str, dict[str, int]] = {}

    start_total_time = time.perf_counter()
    latencies: list[float] = []

    for item in eval_questions:
        expected = str(item["answer"]).strip().upper()
        topic = str(item.get("topic", "")).strip()
        if topic and topic not in topic_stats:
            topic_stats[topic] = {"total": 0, "correct": 0}

        parsed = ParsedQuestion(
            question=item["question"],
            options=item["options"],
        )

        q_start = time.perf_counter()
        raw_pred = engine.answer(parsed, subject=subject)
        q_elapsed_ms = (time.perf_counter() - q_start) * 1000.0
        latencies.append(q_elapsed_ms)

        pred_cleaned = str(raw_pred).strip().upper()

        # Update predicted letter distribution
        if pred_cleaned in {"A", "B", "C", "D"}:
            pred_distribution[pred_cleaned] += 1
        else:
            pred_distribution["INVALID"] += 1

        is_valid_letter = len(pred_cleaned) == 1 and pred_cleaned in {"A", "B", "C", "D"}

        if topic:
            topic_stats[topic]["total"] += 1

        if not is_valid_letter or pred_cleaned == INVALID_ANSWER:
            invalid_count += 1
            wrong += 1
            wrong_questions.append(
                {
                    "id": item.get("id"),
                    "question": item.get("question", "")[:60],
                    "expected": expected,
                    "predicted": raw_pred,
                    "reason": "Invalid response format (no single letter A-D)",
                }
            )
        elif pred_cleaned == expected:
            correct += 1
            if topic:
                topic_stats[topic]["correct"] += 1
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
    avg_lat, p50_lat, p95_lat = compute_latencies(latencies)
    accuracy_pct = (correct / total) * 100.0 if total > 0 else 0.0

    # Format topic accuracy breakdown
    topic_accuracy: dict[str, dict[str, Any]] = {}
    for t_name, t_data in topic_stats.items():
        t_tot = t_data["total"]
        t_cor = t_data["correct"]
        t_pct = (t_cor / t_tot * 100.0) if t_tot > 0 else 0.0
        topic_accuracy[t_name] = {
            "total": t_tot,
            "correct": t_cor,
            "accuracy_pct": round(t_pct, 1),
        }

    _, balance_warning = check_dataset_balance(eval_questions)

    return EvalResult(
        subject_name=subject.name if subject else "General",
        engine_name=engine_name,
        model_name=model_name,
        total=total,
        correct=correct,
        wrong=wrong,
        invalid_count=invalid_count,
        accuracy_pct=accuracy_pct,
        avg_latency_ms=avg_lat,
        p50_latency_ms=p50_lat,
        p95_latency_ms=p95_lat,
        total_time_sec=total_time_sec,
        predicted_distribution=pred_distribution,
        topic_accuracy=topic_accuracy,
        split=split,
        balance_warning=balance_warning,
        wrong_questions=wrong_questions,
    )


def print_report(res: EvalResult) -> None:
    """Print a clean CLI summary report."""
    border = "=" * 65
    print("\n" + border)
    print(f" netPrep Evaluation Report: {res.subject_name}")
    print(f" Engine: {res.engine_name} | Model: {res.model_name}")
    if res.split:
        print(f" Split : {res.split}")
    print(border)
    print(f" Total Questions      : {res.total}")
    print(f" Correct Answers      : {res.correct}")
    print(f" Wrong Answers        : {res.wrong}")
    print(f" Invalid Answers      : {res.invalid_count} (no letter or multiple letters)")
    print(f" Overall Accuracy     : {res.accuracy_pct:.1f}% ({res.correct}/{res.total})")
    print("-" * 65)
    print(f" Latency - Average    : {res.avg_latency_ms:.2f} ms")
    print(f" Latency - Median(p50): {res.p50_latency_ms:.2f} ms")
    print(f" Latency - p95        : {res.p95_latency_ms:.2f} ms")
    print(f" Total Time           : {res.total_time_sec:.3f} s")
    print("-" * 65)

    print(" Predicted Letter Distribution:")
    for letter, count in res.predicted_distribution.items():
        pct = (count / res.total * 100.0) if res.total > 0 else 0.0
        print(f"   [{letter}]: {count:2d} ({pct:5.1f}%)")

    if res.topic_accuracy:
        print("-" * 65)
        print(" Per-Topic Accuracy:")
        for topic, stats in res.topic_accuracy.items():
            print(f"   - {topic}: {stats['accuracy_pct']:.1f}% ({stats['correct']}/{stats['total']})")

    if res.balance_warning:
        print("-" * 65)
        print(f" [!] WARNING: {res.balance_warning}")

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


def print_comparison_table(res_a: EvalResult, res_b: EvalResult) -> None:
    """Print a side-by-side comparison table between two evaluation results."""
    border = "=" * 75
    col_w = 24
    print("\n" + border)
    print(f" netPrep Model Comparison: {res_a.model_name} vs. {res_b.model_name}")
    print(border)
    header = f" {'Metric':<25} | {res_a.model_name:<{col_w}} | {res_b.model_name:<{col_w}}"
    print(header)
    print("-" * 75)

    rows = [
        ("Subject", res_a.subject_name, res_b.subject_name),
        ("Total Questions", str(res_a.total), str(res_b.total)),
        (
            "Overall Accuracy",
            f"{res_a.accuracy_pct:.1f}% ({res_a.correct}/{res_a.total})",
            f"{res_b.accuracy_pct:.1f}% ({res_b.correct}/{res_b.total})",
        ),
        ("Invalid Answers", str(res_a.invalid_count), str(res_b.invalid_count)),
        ("Avg Latency (ms)", f"{res_a.avg_latency_ms:.2f} ms", f"{res_b.avg_latency_ms:.2f} ms"),
        ("Median Latency (p50)", f"{res_a.p50_latency_ms:.2f} ms", f"{res_b.p50_latency_ms:.2f} ms"),
        ("p95 Latency (ms)", f"{res_a.p95_latency_ms:.2f} ms", f"{res_b.p95_latency_ms:.2f} ms"),
        ("Total Time", f"{res_a.total_time_sec:.3f} s", f"{res_b.total_time_sec:.3f} s"),
    ]

    for label, val_a, val_b in rows:
        print(f" {label:<25} | {val_a:<{col_w}} | {val_b:<{col_w}}")
    print(border + "\n")


def save_eval_result(result: EvalResult, out_dir: Path | None = None) -> Path:
    """Save evaluation summary JSON into docs/reports/eval-results/."""
    target_dir = out_dir or (workspace_root / "docs" / "reports" / "eval-results")
    target_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    clean_model = result.model_name.replace(":", "_").replace("/", "_")
    filename = f"eval_{result.engine_name}_{clean_model}_{timestamp}.json"
    dest = target_dir / filename

    data = result.to_dict()
    data["timestamp"] = datetime.datetime.now().isoformat()

    dest.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return dest


def main() -> None:
    """Parse CLI options, validate dataset, run evaluation, and output results."""
    parser = argparse.ArgumentParser(
        description="Run evaluation on netPrep multiple-choice question datasets."
    )
    parser.add_argument(
        "--subject",
        default="computer_networks",
        help="Subject pack identifier in subjects/ (default: computer_networks)",
    )
    parser.add_argument(
        "--engine",
        default="dummy",
        choices=["dummy", "ollama"],
        help="AnswerEngine implementation (default: dummy)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model name for Ollama engine (e.g. qwen2.5:1.5b)",
    )
    parser.add_argument(
        "--split",
        default=None,
        choices=["dev", "holdout"],
        help="Optional dataset split to evaluate (dev or holdout)",
    )
    parser.add_argument(
        "--eval-file",
        default=None,
        help="Custom path to an eval questions.json file",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save evaluation result JSON to docs/reports/eval-results/",
    )
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("MODEL_A", "MODEL_B"),
        help="Run comparison mode between two models (e.g. --compare qwen2.5:1.5b llama3.2:1b)",
    )
    args = parser.parse_args()

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

    # Comparison Mode
    if args.compare:
        m_a, m_b = args.compare[0], args.compare[1]
        print(f"Running comparison between Model A: '{m_a}' and Model B: '{m_b}'...")
        try:
            eng_a = resolve_engine(args.engine, model_name=m_a)
            res_a = run_evaluation(
                content, engine=eng_a, subject=subject, engine_name=args.engine, model_name=m_a, split=args.split
            )
            eng_b = resolve_engine(args.engine, model_name=m_b)
            res_b = run_evaluation(
                content, engine=eng_b, subject=subject, engine_name=args.engine, model_name=m_b, split=args.split
            )
        except (OllamaConnectionError, OllamaModelNotFoundError, OllamaTimeoutError) as exc:
            sys.stderr.write(f"\n[ERROR] Comparison aborted: {exc}\n\n")
            sys.exit(1)

        print_comparison_table(res_a, res_b)
        if args.save:
            p_a = save_eval_result(res_a)
            p_b = save_eval_result(res_b)
            print(f"Saved comparison results to:\n  - {p_a}\n  - {p_b}")
        return

    model_label = args.model or ("dummy" if args.engine == "dummy" else "qwen2.5:1.5b")
    try:
        engine = resolve_engine(args.engine, model_name=model_label)
        result = run_evaluation(
            content,
            engine=engine,
            subject=subject,
            engine_name=args.engine,
            model_name=model_label,
            split=args.split,
        )
    except (OllamaConnectionError, OllamaModelNotFoundError, OllamaTimeoutError) as exc:
        sys.stderr.write(f"\n[ERROR] Evaluation aborted: {exc}\n\n")
        sys.exit(1)
    except ValueError as exc:
        sys.stderr.write(f"Error: {exc}\n")
        sys.exit(1)
    print_report(result)

    if args.save:
        saved_path = save_eval_result(result)
        print(f"Saved evaluation result to: {saved_path}\n")


if __name__ == "__main__":
    main()
