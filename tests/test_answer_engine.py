"""Unit tests for netprep.answer_engine (OllamaAnswerEngine and letter extraction)."""

from __future__ import annotations

import io
import json
import socket
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

from netprep.answer_engine import (
    INVALID_ANSWER,
    OllamaAnswerEngine,
    OllamaConnectionError,
    OllamaModelNotFoundError,
    OllamaTimeoutError,
    extract_answer_letter,
)
from netprep.config import AppConfig
from netprep.scan_pipeline import ParsedQuestion
from netprep.subjects import SubjectPack


class TestAnswerLetterExtraction(unittest.TestCase):
    """Test extraction of single answer letter from clean, messy, and invalid replies."""

    def test_single_clean_letters(self) -> None:
        self.assertEqual(extract_answer_letter("B"), "B")
        self.assertEqual(extract_answer_letter("A"), "A")
        self.assertEqual(extract_answer_letter("c"), "C")
        self.assertEqual(extract_answer_letter("D"), "D")

    def test_single_letter_with_punctuation(self) -> None:
        self.assertEqual(extract_answer_letter("B."), "B")
        self.assertEqual(extract_answer_letter("(B)"), "B")
        self.assertEqual(extract_answer_letter("B:"), "B")
        self.assertEqual(extract_answer_letter("  A.  "), "A")

    def test_prefixed_answers(self) -> None:
        self.assertEqual(extract_answer_letter("Answer: B"), "B")
        self.assertEqual(extract_answer_letter("The answer is B because it operates at Layer 3."), "B")
        self.assertEqual(extract_answer_letter("Correct answer: (C)"), "C")
        self.assertEqual(extract_answer_letter("Option: D"), "D")

    def test_structured_json_reply(self) -> None:
        self.assertEqual(extract_answer_letter('{"answer": "B"}'), "B")
        self.assertEqual(extract_answer_letter('{"answer": "c"}'), "C")

    def test_empty_or_whitespace_reply(self) -> None:
        self.assertEqual(extract_answer_letter(""), INVALID_ANSWER)
        self.assertEqual(extract_answer_letter("   \n\t  "), INVALID_ANSWER)

    def test_ambiguous_two_letters_replies(self) -> None:
        self.assertEqual(extract_answer_letter("A and B"), INVALID_ANSWER)
        self.assertEqual(extract_answer_letter("Either C or D"), INVALID_ANSWER)
        self.assertEqual(extract_answer_letter("AB"), INVALID_ANSWER)

    def test_no_letter_in_reply(self) -> None:
        self.assertEqual(extract_answer_letter("I do not know the answer."), INVALID_ANSWER)
        self.assertEqual(extract_answer_letter("Here is an explanation of networking."), INVALID_ANSWER)


class TestOllamaAnswerEngine(unittest.TestCase):
    """Test OllamaAnswerEngine prompt rendering, mock responses, and custom errors."""

    def setUp(self) -> None:
        self.engine = OllamaAnswerEngine(
            model_name="qwen2.5:1.5b",
            host="http://localhost:11434",
            timeout=5.0,
            keep_alive="5m",
        )
        self.question = ParsedQuestion(
            question="Which protocol resolves IPv4 addresses to MAC addresses?",
            options={"A": "DNS", "B": "ARP", "C": "DHCP", "D": "ICMP"},
        )
        self.subject = SubjectPack(
            id="computer_networks",
            name="Computer Networks",
            description="Networking protocols",
            prompt_hint="Focus on Ethernet, IP addressing, and OSI layer responsibilities.",
            path=Path("subjects/computer_networks"),
            notes_dir=Path("subjects/computer_networks/notes"),
            eval_file=Path("subjects/computer_networks/eval/questions.json"),
        )

    def test_prompt_formatting_includes_hint_and_options(self) -> None:
        prompt = self.engine._format_prompt(self.question, self.subject)
        self.assertIn("Focus on Ethernet", prompt)
        self.assertIn("Which protocol resolves IPv4 addresses", prompt)
        self.assertIn("B. ARP", prompt)

    @patch("urllib.request.urlopen")
    def test_successful_structured_answer(self, mock_urlopen: MagicMock) -> None:
        fake_response = json.dumps({"response": '{"answer": "B"}'}).encode("utf-8")
        mock_resp = MagicMock()
        mock_resp.read.return_value = fake_response
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        ans = self.engine.answer(self.question, self.subject)
        self.assertEqual(ans, "B")

    @patch("urllib.request.urlopen")
    def test_invalid_answer_returns_invalid_constant(self, mock_urlopen: MagicMock) -> None:
        fake_response = json.dumps({"response": "I cannot answer this question."}).encode("utf-8")
        mock_resp = MagicMock()
        mock_resp.read.return_value = fake_response
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        ans = self.engine.answer(self.question, self.subject)
        self.assertEqual(ans, INVALID_ANSWER)

    @patch("urllib.request.urlopen")
    def test_connection_error_includes_exact_fix(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
        with self.assertRaises(OllamaConnectionError) as ctx:
            self.engine.answer(self.question, self.subject)
        self.assertIn("run: ollama serve", str(ctx.exception))

    @patch("urllib.request.urlopen")
    def test_model_missing_error_includes_exact_fix(self, mock_urlopen: MagicMock) -> None:
        http_err = urllib.error.HTTPError(
            url="http://localhost:11434/api/generate",
            code=404,
            msg="Not Found",
            hdrs={},  # type: ignore[arg-type]
            fp=io.BytesIO(b'{"error": "model not found"}'),
        )
        mock_urlopen.side_effect = http_err
        with self.assertRaises(OllamaModelNotFoundError) as ctx:
            self.engine.answer(self.question, self.subject)
        self.assertIn("run: ollama pull qwen2.5:1.5b", str(ctx.exception))

    @patch("urllib.request.urlopen")
    def test_timeout_error(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.side_effect = socket.timeout("timed out")
        with self.assertRaises(OllamaTimeoutError) as ctx:
            self.engine.answer(self.question, self.subject)
        self.assertIn("timed out after 5.0s", str(ctx.exception))

    @patch("urllib.request.urlopen")
    def test_warmup_success(self, mock_urlopen: MagicMock) -> None:
        fake_response = json.dumps({"response": ""}).encode("utf-8")
        mock_resp = MagicMock()
        mock_resp.read.return_value = fake_response
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        self.assertTrue(self.engine.warmup())

    @patch("urllib.request.urlopen")
    def test_warmup_connection_failure_returns_false_without_raising(
        self, mock_urlopen: MagicMock
    ) -> None:
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
        self.assertFalse(self.engine.warmup())


class TestConfigDefaults(unittest.TestCase):
    """Test configuration defaults for Ollama settings."""

    def test_app_config_ollama_defaults(self) -> None:
        cfg = AppConfig()
        self.assertEqual(cfg.model_name, "qwen2.5:1.5b")
        self.assertEqual(cfg.ollama_host, "http://localhost:11434")
        self.assertEqual(cfg.ollama_timeout, 15.0)
        self.assertEqual(cfg.ollama_keep_alive, "5m")


if __name__ == "__main__":
    unittest.main()
