#!/usr/bin/env python3
"""Developer verification script for netPrep answer engine.

Takes a multiple-choice question and options from CLI arguments or a JSON file,
sends it to the AnswerEngine (Ollama or Dummy), and prints the predicted answer
letter and inference latency.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Ensure workspace root is in sys.path
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
from netprep.scan_pipeline import DummyAnswerEngine, ParsedQuestion
from netprep.subjects import get_subject_pack


def main() -> None:
    """Parse question inputs, run answer engine, and display results."""
    parser = argparse.ArgumentParser(
        description="Verify netPrep AnswerEngine on a single multiple-choice question."
    )
    parser.add_argument("--question", default=None, help="The question text.")
    parser.add_argument("--a", default=None, help="Option A text.")
    parser.add_argument("--b", default=None, help="Option B text.")
    parser.add_argument("--c", default=None, help="Option C text.")
    parser.add_argument("--d", default=None, help="Option D text.")
    parser.add_argument("--file", default=None, help="Path to JSON file containing question.")
    parser.add_argument(
        "--engine",
        default="ollama",
        choices=["ollama", "dummy"],
        help="Answer engine to use (default: ollama)",
    )
    parser.add_argument(
        "--model",
        default="qwen2.5:1.5b",
        help="Ollama model name (default: qwen2.5:1.5b)",
    )
    parser.add_argument(
        "--host",
        default="http://localhost:11434",
        help="Ollama host URL (default: http://localhost:11434)",
    )
    parser.add_argument(
        "--subject",
        default="computer_networks",
        help="Subject pack identifier (default: computer_networks)",
    )
    args = parser.parse_args()

    q_text: str = ""
    options: dict[str, str] = {}

    if args.file:
        file_path = Path(args.file).resolve()
        if not file_path.exists():
            sys.stderr.write(f"Error: Question file not found at: {file_path}\n")
            sys.exit(1)
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            if isinstance(data, list) and len(data) > 0:
                data = data[0]
            q_text = str(data.get("question", "")).strip()
            options = {k.upper(): str(v).strip() for k, v in data.get("options", {}).items()}
        except Exception as exc:
            sys.stderr.write(f"Error parsing JSON from {file_path}: {exc}\n")
            sys.exit(1)
    else:
        if not args.question or not args.a or not args.b or not args.c or not args.d:
            sys.stderr.write(
                "Error: Must provide either --file PATH or all of (--question, --a, --b, --c, --d).\n"
            )
            sys.exit(1)
        q_text = args.question.strip()
        options = {
            "A": args.a.strip(),
            "B": args.b.strip(),
            "C": args.c.strip(),
            "D": args.d.strip(),
        }

    parsed = ParsedQuestion(question=q_text, options=options)
    val_errs = parsed.validate()
    if val_errs:
        sys.stderr.write("Invalid question structure:\n")
        for err in val_errs:
            sys.stderr.write(f"  - {err}\n")
        sys.exit(1)

    subjects_dir = workspace_root / "subjects"
    subject = get_subject_pack(args.subject, subjects_dir)

    print("\n" + "=" * 65)
    print(" netPrep Answer Engine Verification")
    print("=" * 65)
    print(f" Subject : {subject.name if subject else args.subject}")
    print(f" Engine  : {args.engine} | Model: {args.model if args.engine == 'ollama' else 'n/a'}")
    print("-" * 65)
    print(f" Question: \"{q_text}\"")
    print(" Options :")
    for letter in ["A", "B", "C", "D"]:
        print(f"   [{letter}] {options.get(letter, '')}")
    print("-" * 65)

    if args.engine == "dummy":
        engine = DummyAnswerEngine()
    else:
        engine = OllamaAnswerEngine(model_name=args.model, host=args.host)

    t0 = time.perf_counter()
    try:
        answer = engine.answer(parsed, subject=subject)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
    except OllamaConnectionError as conn_err:
        sys.stderr.write(f"\n[ERROR] Connection failed: {conn_err}\n\n")
        sys.exit(1)
    except OllamaModelNotFoundError as model_err:
        sys.stderr.write(f"\n[ERROR] Model missing: {model_err}\n\n")
        sys.exit(1)
    except OllamaTimeoutError as timeout_err:
        sys.stderr.write(f"\n[ERROR] Timeout: {timeout_err}\n\n")
        sys.exit(1)
    except Exception as exc:
        sys.stderr.write(f"\n[ERROR] Unexpected inference failure: {exc}\n\n")
        sys.exit(1)

    status = "SUCCESS" if answer in {"A", "B", "C", "D"} else "INVALID ANSWER"
    print(f" Status          : {status}")
    print(f" Predicted Answer: [{answer}]")
    print(f" Inference Time  : {elapsed_ms:.2f} ms")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
