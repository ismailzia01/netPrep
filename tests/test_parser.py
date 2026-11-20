"""Unit tests for netprep.parser (QuestionParser and RegexQuestionParser)."""

from __future__ import annotations

import unittest

from netprep.ocr import OcrLine
from netprep.parser import QuestionNotFoundError, RegexQuestionParser
from netprep.scan_pipeline import BoundingBox


def _make_line(text: str, y: int = 0, h: int = 20) -> OcrLine:
    """Helper to create an OcrLine with realistic bounding boxes."""
    return OcrLine(
        text=text,
        confidence=0.98,
        box_px=BoundingBox(x=10, y=y, width=400, height=h),
        box_points=BoundingBox(x=5, y=y // 2, width=200, height=h // 2),
    )


class TestRegexQuestionParser(unittest.TestCase):
    """Test suite for RegexQuestionParser."""

    def setUp(self) -> None:
        self.parser = RegexQuestionParser()

    def test_standard_dot_marker(self) -> None:
        """Parse standard 'A.', 'B.', 'C.', 'D.' format."""
        raw_lines = [
            _make_line("What is the primary role of the router?", y=20),
            _make_line("A. Forward packets across networks", y=60),
            _make_line("B. Terminate physical cable connections", y=100),
            _make_line("C. Assign MAC addresses to devices", y=140),
            _make_line("D. Modulate analog audio signals", y=180),
        ]
        parsed = self.parser.parse(raw_lines)
        self.assertEqual(parsed.question, "What is the primary role of the router?")
        self.assertEqual(parsed.options["A"], "Forward packets across networks")
        self.assertEqual(parsed.options["B"], "Terminate physical cable connections")
        self.assertEqual(parsed.options["C"], "Assign MAC addresses to devices")
        self.assertEqual(parsed.options["D"], "Modulate analog audio signals")

    def test_parentheses_markers(self) -> None:
        """Parse 'A)', 'B)', 'C)', 'D)' and '(A)', '(B)', '(C)', '(D)'."""
        lines_closing_paren = [
            _make_line("Identify the transport layer protocol:", y=20),
            _make_line("A) TCP", y=60),
            _make_line("B) IP", y=100),
            _make_line("C) Ethernet", y=140),
            _make_line("D) ICMP", y=180),
        ]
        parsed1 = self.parser.parse(lines_closing_paren)
        self.assertEqual(parsed1.options["A"], "TCP")
        self.assertEqual(parsed1.options["B"], "IP")

        lines_both_parens = [
            _make_line("Identify the transport layer protocol:", y=20),
            _make_line("(A) TCP", y=60),
            _make_line("(B) IP", y=100),
            _make_line("(C) Ethernet", y=140),
            _make_line("(D) ICMP", y=180),
        ]
        parsed2 = self.parser.parse(lines_both_parens)
        self.assertEqual(parsed2.options["A"], "TCP")
        self.assertEqual(parsed2.options["C"], "Ethernet")

    def test_colon_and_lowercase_markers(self) -> None:
        """Parse 'A:', 'B:', 'C:', 'D:' and lowercase 'a)', 'b)', 'c)', 'd)'."""
        lines_colon = [
            _make_line("Select the connectionless protocol:", y=20),
            _make_line("A: UDP", y=60),
            _make_line("B: TCP", y=100),
            _make_line("C: SSH", y=140),
            _make_line("D: TLS", y=180),
        ]
        parsed1 = self.parser.parse(lines_colon)
        self.assertEqual(parsed1.options["A"], "UDP")

        lines_lower = [
            _make_line("Select the connectionless protocol:", y=20),
            _make_line("a) UDP", y=60),
            _make_line("b) TCP", y=100),
            _make_line("c) SSH", y=140),
            _make_line("d) TLS", y=180),
        ]
        parsed2 = self.parser.parse(lines_lower)
        self.assertEqual(parsed2.options["A"], "UDP")
        self.assertEqual(parsed2.options["D"], "TLS")

    def test_multiline_question_and_options(self) -> None:
        """Ensure multi-line questions and wrapped option lines are concatenated properly."""
        raw_lines = [
            _make_line("A network engineer is configuring a core router", y=20),
            _make_line("and needs to ensure low latency for voice traffic.", y=40),
            _make_line("Which QoS mechanism should be applied?", y=60),
            _make_line("A. Strict priority queuing", y=100),
            _make_line("for real-time packets", y=120),
            _make_line("B. Best-effort FIFO dispatching", y=160),
            _make_line("C. Weighted round robin with low weight", y=200),
            _make_line("D. Random early detection discard only", y=240),
        ]
        parsed = self.parser.parse(raw_lines)
        expected_stem = (
            "A network engineer is configuring a core router "
            "and needs to ensure low latency for voice traffic. "
            "Which QoS mechanism should be applied?"
        )
        self.assertEqual(parsed.question, expected_stem)
        self.assertEqual(parsed.options["A"], "Strict priority queuing for real-time packets")
        self.assertEqual(parsed.options["B"], "Best-effort FIFO dispatching")

        # Check option bounding box union covers both lines for Option A
        box_a = parsed.option_boxes["A"]
        # Screen box y for line 100 is 50, h is 10. For line 120, y is 60, h is 10.
        # Enclosing box y should be 50, height should be 20.
        self.assertEqual(box_a.y, 50)
        self.assertEqual(box_a.height, 20)

    def test_top_and_bottom_ui_noise_filtering(self) -> None:
        """Verify headers, timers, counters, and bottom navigation buttons are stripped."""
        raw_lines = [
            _make_line("14:59 Remaining", y=10),
            _make_line("Question 4 of 25", y=30),
            _make_line("Score: 10 pts", y=50),
            _make_line("What is the broadcast MAC address?", y=80),
            _make_line("A. FF:FF:FF:FF:FF:FF", y=120),
            _make_line("B. 00:00:00:00:00:00", y=150),
            _make_line("C. 01:00:5E:00:00:01", y=180),
            _make_line("D. 127.0.0.1", y=210),
            _make_line("Next Question", y=260),
            _make_line("Submit Answer", y=290),
        ]
        parsed = self.parser.parse(raw_lines)
        self.assertEqual(parsed.question, "What is the broadcast MAC address?")
        self.assertEqual(parsed.options["A"], "FF:FF:FF:FF:FF:FF")
        self.assertEqual(parsed.options["D"], "127.0.0.1")

    def test_missing_option_raises_question_not_found(self) -> None:
        """When an option is missing (e.g. only A, B, C), raise QuestionNotFoundError."""
        raw_lines = [
            _make_line("Incomplete question:", y=20),
            _make_line("A. First option", y=60),
            _make_line("B. Second option", y=100),
            _make_line("C. Third option", y=140),
        ]
        with self.assertRaises(QuestionNotFoundError) as ctx:
            self.parser.parse(raw_lines)
        self.assertIn("Expected exactly 4 sequential options", str(ctx.exception))

    def test_five_options_raises_question_not_found(self) -> None:
        """When 5 options (A-E) exist, raise QuestionNotFoundError without guessing."""
        raw_lines = [
            _make_line("Question with 5 choices:", y=20),
            _make_line("A. Opt A", y=50),
            _make_line("B. Opt B", y=80),
            _make_line("C. Opt C", y=110),
            _make_line("D. Opt D", y=140),
            _make_line("E. Opt E", y=170),
        ]
        with self.assertRaises(QuestionNotFoundError) as ctx:
            self.parser.parse(raw_lines)
        self.assertIn("Expected exactly 4 sequential options", str(ctx.exception))

    def test_duplicate_option_letters_raises_question_not_found(self) -> None:
        """Duplicate option letters trigger QuestionNotFoundError."""
        raw_lines = [
            _make_line("Duplicate question:", y=20),
            _make_line("A. First option", y=50),
            _make_line("B. Second option", y=80),
            _make_line("B. Third option repeat", y=110),
            _make_line("C. Fourth option", y=140),
            _make_line("D. Fifth option", y=170),
        ]
        with self.assertRaises(QuestionNotFoundError) as ctx:
            self.parser.parse(raw_lines)
        self.assertIn("Duplicate option letters detected", str(ctx.exception))

    def test_empty_or_whitespace_input_raises_question_not_found(self) -> None:
        """Empty input raises QuestionNotFoundError."""
        with self.assertRaises(QuestionNotFoundError):
            self.parser.parse([])

        with self.assertRaises(QuestionNotFoundError):
            self.parser.parse([_make_line("   ", y=10), _make_line("", y=30)])

    def test_missing_question_stem_raises_question_not_found(self) -> None:
        """If Option A starts on the very first non-noise line, QuestionNotFoundError is raised."""
        raw_lines = [
            _make_line("Question 1 of 5", y=10),  # Noise line
            _make_line("A. Opt A", y=50),
            _make_line("B. Opt B", y=80),
            _make_line("C. Opt C", y=110),
            _make_line("D. Opt D", y=140),
        ]
        with self.assertRaises(QuestionNotFoundError) as ctx:
            self.parser.parse(raw_lines)
        self.assertIn("No question stem found", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
