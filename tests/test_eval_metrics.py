"""Unit tests for evaluation metrics, percentiles, distributions, and dataset validation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from netprep.scan_pipeline import DummyAnswerEngine
from scripts.run_eval import (
    EvalResult,
    check_dataset_balance,
    compute_latencies,
    print_comparison_table,
    run_evaluation,
    save_eval_result,
    validate_eval_questions,
)


class TestEvalMetrics(unittest.TestCase):
    """Test latency percentiles, predicted letter distribution, and per-topic accuracy."""

    def test_compute_latencies_odd_and_even(self) -> None:
        # Odd count: [100, 200, 300]
        avg, p50, p95 = compute_latencies([100.0, 200.0, 300.0])
        self.assertEqual(avg, 200.0)
        self.assertEqual(p50, 200.0)
        self.assertEqual(p95, 300.0)

        # Even count: [10, 20, 30, 40]
        avg, p50, p95 = compute_latencies([10.0, 20.0, 30.0, 40.0])
        self.assertEqual(avg, 25.0)
        self.assertEqual(p50, 25.0)
        self.assertEqual(p95, 40.0)

        # Empty list
        self.assertEqual(compute_latencies([]), (0.0, 0.0, 0.0))

    def test_check_dataset_balance(self) -> None:
        # Unbalanced: 3 out of 4 are 'B' (75%)
        unbalanced = [
            {"id": 1, "answer": "B"},
            {"id": 2, "answer": "B"},
            {"id": 3, "answer": "B"},
            {"id": 4, "answer": "A"},
        ]
        counts, warning = check_dataset_balance(unbalanced)
        self.assertEqual(counts["B"], 3)
        self.assertIsNotNone(warning)
        self.assertIn("unbalanced", warning.lower())

        # Balanced: 1 of each
        balanced = [
            {"id": 1, "answer": "A"},
            {"id": 2, "answer": "B"},
            {"id": 3, "answer": "C"},
            {"id": 4, "answer": "D"},
        ]
        counts2, warning2 = check_dataset_balance(balanced)
        self.assertIsNone(warning2)

    def test_topic_breakdown_and_letter_distribution(self) -> None:
        questions = [
            {
                "id": 1,
                "question": "What is ARP?",
                "options": {"A": "1", "B": "2", "C": "3", "D": "4"},
                "answer": "B",
                "topic": "Layer 2",
            },
            {
                "id": 2,
                "question": "What is BGP?",
                "options": {"A": "1", "B": "2", "C": "3", "D": "4"},
                "answer": "B",
                "topic": "Routing",
            },
            {
                "id": 3,
                "question": "What is TCP?",
                "options": {"A": "1", "B": "2", "C": "3", "D": "4"},
                "answer": "A",
                "topic": "Routing",
            },
        ]
        engine = DummyAnswerEngine(default_answer="B")
        res = run_evaluation(questions, engine=engine)

        self.assertEqual(res.total, 3)
        self.assertEqual(res.correct, 2)
        self.assertEqual(res.wrong, 1)
        self.assertEqual(res.predicted_distribution["B"], 3)
        self.assertEqual(res.predicted_distribution["A"], 0)

        # Check topic breakdown
        self.assertIn("Layer 2", res.topic_accuracy)
        self.assertEqual(res.topic_accuracy["Layer 2"]["accuracy_pct"], 100.0)
        self.assertIn("Routing", res.topic_accuracy)
        self.assertEqual(res.topic_accuracy["Routing"]["correct"], 1)
        self.assertEqual(res.topic_accuracy["Routing"]["total"], 2)
        self.assertEqual(res.topic_accuracy["Routing"]["accuracy_pct"], 50.0)

    def test_split_filtering(self) -> None:
        questions = [
            {
                "id": 1,
                "question": "Q1",
                "options": {"A": "1", "B": "2", "C": "3", "D": "4"},
                "answer": "B",
                "split": "dev",
            },
            {
                "id": 2,
                "question": "Q2",
                "options": {"A": "1", "B": "2", "C": "3", "D": "4"},
                "answer": "B",
                "split": "holdout",
            },
        ]
        engine = DummyAnswerEngine(default_answer="B")

        res_dev = run_evaluation(questions, engine=engine, split="dev")
        self.assertEqual(res_dev.total, 1)

        res_holdout = run_evaluation(questions, engine=engine, split="holdout")
        self.assertEqual(res_holdout.total, 1)

        res_all = run_evaluation(questions, engine=engine, split=None)
        self.assertEqual(res_all.total, 2)


class TestValidationAndPersistence(unittest.TestCase):
    """Test dataset validation and saving result JSON."""

    def test_validation_with_valid_and_missing_split(self) -> None:
        # Valid without split
        valid_no_split = [
            {"id": 1, "question": "Q?", "options": {"A": "1", "B": "2", "C": "3", "D": "4"}, "answer": "B"}
        ]
        self.assertEqual(validate_eval_questions(valid_no_split), [])

        # Valid with split and topic
        valid_with_split = [
            {
                "id": 1,
                "question": "Q?",
                "options": {"A": "1", "B": "2", "C": "3", "D": "4"},
                "answer": "B",
                "split": "dev",
                "topic": "Transport",
            }
        ]
        self.assertEqual(validate_eval_questions(valid_with_split), [])

        # Invalid split value
        invalid_split = [
            {
                "id": 1,
                "question": "Q?",
                "options": {"A": "1", "B": "2", "C": "3", "D": "4"},
                "answer": "B",
                "split": "train",
            }
        ]
        errors = validate_eval_questions(invalid_split)
        self.assertTrue(any("split" in e for e in errors))

    def test_save_eval_result(self) -> None:
        result = EvalResult(
            subject_name="Computer Networks",
            engine_name="dummy",
            model_name="dummy",
            total=3,
            correct=2,
            wrong=1,
            invalid_count=0,
            accuracy_pct=66.7,
            avg_latency_ms=1.5,
            p50_latency_ms=1.4,
            p95_latency_ms=2.0,
            total_time_sec=0.01,
            predicted_distribution={"A": 0, "B": 3, "C": 0, "D": 0, "INVALID": 0},
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = save_eval_result(result, out_dir=Path(tmp_dir))
            self.assertTrue(out_path.exists())
            loaded = out_path.read_text(encoding="utf-8")
            self.assertIn("accuracy_pct", loaded)
            self.assertIn("p50_latency_ms", loaded)

    def test_comparison_table_generation(self) -> None:
        res1 = EvalResult(
            subject_name="CN",
            engine_name="dummy",
            model_name="ModelA",
            total=3,
            correct=2,
            wrong=1,
            invalid_count=0,
            accuracy_pct=66.7,
            avg_latency_ms=10.0,
            p50_latency_ms=9.0,
            p95_latency_ms=12.0,
            total_time_sec=0.03,
            predicted_distribution={},
        )
        res2 = EvalResult(
            subject_name="CN",
            engine_name="dummy",
            model_name="ModelB",
            total=3,
            correct=1,
            wrong=2,
            invalid_count=0,
            accuracy_pct=33.3,
            avg_latency_ms=15.0,
            p50_latency_ms=14.0,
            p95_latency_ms=18.0,
            total_time_sec=0.04,
            predicted_distribution={},
        )
        # Verify print_comparison_table does not crash
        print_comparison_table(res1, res2)


if __name__ == "__main__":
    unittest.main()
