"""Unit tests for evaluation dataset format and validation rules."""

import json
import unittest
from pathlib import Path

from netprep.scan_pipeline import DummyAnswerEngine
from scripts.run_eval import run_evaluation, validate_eval_questions


class TestEvalFormat(unittest.TestCase):
    def test_real_computer_networks_eval_is_valid(self) -> None:
        eval_file = Path("subjects/computer_networks/eval/questions.json")
        self.assertTrue(eval_file.exists())

        data = json.loads(eval_file.read_text(encoding="utf-8"))
        errors = validate_eval_questions(data)
        self.assertEqual(errors, [], f"Validation errors found: {errors}")
        self.assertEqual(len(data), 3)

    def test_validate_detects_duplicate_ids(self) -> None:
        bad_data = [
            {
                "id": 1,
                "question": "Question 1",
                "options": {"A": "1", "B": "2", "C": "3", "D": "4"},
                "answer": "A",
            },
            {
                "id": 1,
                "question": "Question 2",
                "options": {"A": "1", "B": "2", "C": "3", "D": "4"},
                "answer": "B",
            },
        ]
        errors = validate_eval_questions(bad_data)
        self.assertTrue(any("duplicate id" in err.lower() for err in errors))

    def test_validate_detects_invalid_options(self) -> None:
        bad_data = [
            {
                "id": 1,
                "question": "Question 1",
                "options": {"A": "1", "B": "2", "C": "3"},
                "answer": "A",
            }
        ]
        errors = validate_eval_questions(bad_data)
        self.assertTrue(any("options keys must be exactly" in err for err in errors))

    def test_validate_detects_invalid_answer_letter(self) -> None:
        bad_data = [
            {
                "id": 1,
                "question": "Question 1",
                "options": {"A": "1", "B": "2", "C": "3", "D": "4"},
                "answer": "E",
            }
        ]
        errors = validate_eval_questions(bad_data)
        self.assertTrue(any("'answer' must be one of" in err for err in errors))

    def test_validate_detects_non_list_or_empty(self) -> None:
        self.assertGreater(len(validate_eval_questions({})), 0)
        self.assertGreater(len(validate_eval_questions([])), 0)

    def test_run_evaluation_metrics(self) -> None:
        dataset = [
            {
                "id": 1,
                "question": "Q1",
                "options": {"A": "optA", "B": "optB", "C": "optC", "D": "optD"},
                "answer": "B",
            },
            {
                "id": 2,
                "question": "Q2",
                "options": {"A": "optA", "B": "optB", "C": "optC", "D": "optD"},
                "answer": "C",
            },
        ]
        engine = DummyAnswerEngine(default_answer="B")
        result = run_evaluation(dataset, engine=engine, engine_name="dummy")

        self.assertEqual(result.total, 2)
        self.assertEqual(result.correct, 1)
        self.assertEqual(result.wrong, 1)
        self.assertEqual(result.invalid_count, 0)
        self.assertEqual(result.accuracy_pct, 50.0)
        self.assertEqual(len(result.wrong_questions), 1)
        self.assertEqual(result.wrong_questions[0]["id"], 2)


if __name__ == "__main__":
    unittest.main()
