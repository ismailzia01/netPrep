"""Pipeline interfaces and stub implementations for netPrep.

Stages:
1. ScreenCapturer: captures on-screen quiz area (subject-neutral)
2. OcrEngine: extracts text and spatial metadata (subject-neutral)
3. QuestionParser: parses question text, options A-D, and bounding boxes (subject-neutral)
4. AnswerEngine: determines best answer letter A-D (may use SubjectPack)
5. OverlayRenderer: displays answer indicator on screen (subject-neutral)
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from netprep.subjects import SubjectPack

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BoundingBox:
    """Screen coordinate bounding box for detected elements."""

    x: int
    y: int
    width: int
    height: int

    def to_dict(self) -> dict[str, int]:
        """Convert bounding box to dictionary."""
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}


@dataclass
class ParsedQuestion:
    """Structured representation of a multiple-choice question on screen."""

    question: str
    options: dict[str, str]
    option_boxes: dict[str, BoundingBox] = field(default_factory=dict)
    raw_text: str = ""

    def validate(self) -> list[str]:
        """Validate question structure, returning list of validation errors."""
        errors: list[str] = []
        if not self.question.strip():
            errors.append("Question text is empty.")
        expected_options = {"A", "B", "C", "D"}
        actual_options = set(self.options.keys())
        if actual_options != expected_options:
            errors.append(f"Options must be exactly {expected_options}, got {actual_options}.")
        return errors


class ScreenCapturer(ABC):
    """Abstract interface for screen capture."""

    @abstractmethod
    def capture(self) -> Any:
        """Capture the current screen region containing the question."""
        raise NotImplementedError


class OcrEngine(ABC):
    """Abstract interface for optical character recognition."""

    @abstractmethod
    def extract(self, image: Any) -> Any:
        """Extract text and bounding box locations from the captured image."""
        raise NotImplementedError


class QuestionParser(ABC):
    """Abstract interface for parsing raw OCR output into structured MCQs."""

    @abstractmethod
    def parse(self, raw_ocr_data: Any) -> ParsedQuestion:
        """Parse raw OCR data into a ParsedQuestion."""
        raise NotImplementedError


class AnswerEngine(ABC):
    """Abstract interface for reasoning over questions to predict answer letter.

    Note: This is the ONLY pipeline component permitted to use the subject pack.
    """

    @abstractmethod
    def answer(self, question: ParsedQuestion, subject: SubjectPack | None = None) -> str:
        """Predict the correct answer letter (e.g. 'A', 'B', 'C', or 'D')."""
        raise NotImplementedError


class OverlayRenderer(ABC):
    """Abstract interface for rendering visible answer overlays on screen.

    Design Rule: The overlay is a normal, visible window. It must never attempt
    to hide from screen capture, screen sharing, or recording software.
    """

    @abstractmethod
    def show_answer(self, answer_letter: str, question: ParsedQuestion) -> None:
        """Display the suggested answer on screen."""
        raise NotImplementedError

    @abstractmethod
    def hide(self) -> None:
        """Hide or dismiss the overlay."""
        raise NotImplementedError


# --- Stub Implementations ---


class StubScreenCapturer(ScreenCapturer):
    """Stub implementation returning placeholder capture data."""

    def capture(self) -> dict[str, Any]:
        logger.debug("StubScreenCapturer: capture() invoked.")
        return {"width": 1920, "height": 1080, "pixels": b"stub_pixel_data"}


class StubOcrEngine(OcrEngine):
    """Stub implementation returning mock OCR tokens."""

    def extract(self, image: Any) -> dict[str, Any]:
        logger.debug("StubOcrEngine: extract() invoked.")
        return {
            "text": (
                "Which local broadcast protocol discovers hardware layer-2 addresses for known IPv4 targets?\n"
                "A) DNS\n"
                "B) ARP\n"
                "C) DHCP\n"
                "D) ICMP\n"
            ),
            "tokens": ["Which", "local", "broadcast", "protocol"],
        }


class StubQuestionParser(QuestionParser):
    """Stub implementation returning a standard parsed question."""

    def parse(self, raw_ocr_data: Any) -> ParsedQuestion:
        logger.debug("StubQuestionParser: parse() invoked.")
        return ParsedQuestion(
            question="Which local broadcast protocol discovers hardware layer-2 addresses for known IPv4 targets?",
            options={
                "A": "DNS",
                "B": "ARP",
                "C": "DHCP",
                "D": "ICMP",
            },
            option_boxes={
                "A": BoundingBox(x=100, y=200, width=200, height=30),
                "B": BoundingBox(x=100, y=240, width=200, height=30),
                "C": BoundingBox(x=100, y=280, width=200, height=30),
                "D": BoundingBox(x=100, y=320, width=200, height=30),
            },
            raw_text="Which local broadcast protocol discovers hardware layer-2 addresses for known IPv4 targets?",
        )


class DummyAnswerEngine(AnswerEngine):
    """Dummy engine for tests and evaluation skeleton.

    Returns a deterministic answer (defaults to 'B') or inspects question options.
    """

    def __init__(self, default_answer: str = "B") -> None:
        self.default_answer = default_answer
        self.call_count = 0

    def answer(self, question: ParsedQuestion, subject: SubjectPack | None = None) -> str:
        self.call_count += 1
        subject_name = subject.name if subject else "General"
        logger.debug(
            "DummyAnswerEngine answering for subject '%s' (question: '%s...')",
            subject_name,
            question.question[:30],
        )
        # Verify default answer exists in question options; fallback to first available option
        if self.default_answer in question.options:
            return self.default_answer
        available = sorted(question.options.keys())
        return available[0] if available else "A"


class StubOverlayRenderer(OverlayRenderer):
    """Stub implementation for overlay display."""

    def __init__(self) -> None:
        self.is_visible = False
        self.last_answer: str | None = None

    def show_answer(self, answer_letter: str, question: ParsedQuestion) -> None:
        self.is_visible = True
        self.last_answer = answer_letter
        logger.info(
            "StubOverlayRenderer: Showing answer [%s] for question '%s...'",
            answer_letter,
            question.question[:30],
        )

    def hide(self) -> None:
        self.is_visible = False
        self.last_answer = None
        logger.debug("StubOverlayRenderer: Overlay hidden.")
