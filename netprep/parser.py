"""Question parsing engine extracting 4-option multiple choice questions from OCR output."""

from __future__ import annotations

import logging
import re
from typing import Any

from netprep.ocr import OcrLine
from netprep.scan_pipeline import BoundingBox, ParsedQuestion, QuestionParser

logger = logging.getLogger(__name__)

# Pattern matching: "A.", "A)", "(A)", "A:", "a)", "a.", "(a)", "a:" (and other option letters)
OPTION_MARKER_REGEX = re.compile(
    r"^\s*(?:\(([A-Za-z])\)|([A-Za-z])[.)\]:])(?:\s+(.*)|\s*$)"
)

# UI Noise patterns
TOP_NOISE_REGEX = re.compile(
    r"^\s*(?:"
    r"\d{1,2}:\d{2}(?::\d{2})?\b|"  # e.g., "14:59" or "01:20:15"
    r"time\s*(?:remaining|left)?[:\s]|\b(?:timer|duration)[:\s]|"
    r"question\s+\d+\s*(?:of|/)\s*\d+|"  # e.g., "Question 1 of 20"
    r"q\d+[:.]?|"
    r"score[:\s]|\d+\s*(?:points|pts|marks)|"
    r"exam[:\s]|quiz[:\s]|test[:\s]"
    r")",
    re.IGNORECASE,
)

BOTTOM_NOISE_REGEX = re.compile(
    r"^\s*(?:"
    r"next(?:\s+question)?|"
    r"previous(?:\s+question)?|prev\b|"
    r"submit(?:\s+answer)?|"
    r"mark\s+for\s+review|"
    r"flag(?:\s+question)?|"
    r"finish(?:\s+test)?|"
    r"page\s+\d+\s*(?:of|/)\s*\d+"
    r")\s*$",
    re.IGNORECASE,
)


class QuestionNotFoundError(ValueError):
    """Raised when OCR output does not contain a valid, four-option (A-D) multiple choice question."""


def _compute_bounding_box_union(boxes: list[BoundingBox]) -> BoundingBox:
    """Compute the minimal bounding box enclosing all given bounding boxes."""
    if not boxes:
        return BoundingBox(0, 0, 0, 0)
    min_x = min(b.x for b in boxes)
    min_y = min(b.y for b in boxes)
    max_x = max(b.x + b.width for b in boxes)
    max_y = max(b.y + b.height for b in boxes)
    return BoundingBox(
        x=min_x,
        y=min_y,
        width=max(0, max_x - min_x),
        height=max(0, max_y - min_y),
    )


def _get_line_box(line: Any) -> BoundingBox:
    """Extract preferred screen bounding box from line object or dict."""
    if isinstance(line, OcrLine):
        return line.box_points if line.box_points is not None else line.box_px
    if isinstance(line, dict):
        if "box_points" in line and isinstance(line["box_points"], BoundingBox):
            return line["box_points"]
        if "box" in line and isinstance(line["box"], BoundingBox):
            return line["box"]
    return BoundingBox(0, 0, 0, 0)


def _get_line_text(line: Any) -> str:
    """Extract text string from line object or dict."""
    if isinstance(line, OcrLine):
        return line.text.strip()
    if isinstance(line, dict):
        return str(line.get("text", "")).strip()
    return str(line).strip()


class RegexQuestionParser(QuestionParser):
    """Parses OCR text lines into structured 4-option multiple-choice questions."""

    def parse(self, raw_ocr_data: Any) -> ParsedQuestion:
        """Parse raw OCR data into a ParsedQuestion.

        Raises QuestionNotFoundError if exactly four options (A-D) cannot be confirmed.
        """
        if not raw_ocr_data:
            raise QuestionNotFoundError("No OCR text lines provided.")

        if not isinstance(raw_ocr_data, list):
            raise QuestionNotFoundError(f"Expected list of OCR lines, got {type(raw_ocr_data)}")

        lines = [line for line in raw_ocr_data if _get_line_text(line)]
        if not lines:
            raise QuestionNotFoundError("OCR output contains only empty text.")

        # Identify all candidate option marker lines
        option_candidates: list[dict[str, Any]] = []
        for idx, line in enumerate(lines):
            text = _get_line_text(line)
            match = OPTION_MARKER_REGEX.match(text)
            if match:
                letter = (match.group(1) or match.group(2)).upper()
                remaining = (match.group(3) or "").strip()
                option_candidates.append(
                    {
                        "index": idx,
                        "letter": letter,
                        "initial_text": remaining,
                        "line": line,
                    }
                )

        if not option_candidates:
            raise QuestionNotFoundError("No option markers (A-D) detected in text.")

        # Validate that candidate options match the exact set {'A', 'B', 'C', 'D'} in sequence
        letters_found = [c["letter"] for c in option_candidates]

        # Check for duplicate option letters
        if len(letters_found) != len(set(letters_found)):
            raise QuestionNotFoundError(
                f"Duplicate option letters detected: {letters_found}. Exactly four unique options (A-D) required."
            )

        if letters_found != ["A", "B", "C", "D"]:
            raise QuestionNotFoundError(
                f"Expected exactly 4 sequential options (A, B, C, D), but found {letters_found}."
            )

        idx_a = option_candidates[0]["index"]
        idx_b = option_candidates[1]["index"]
        idx_c = option_candidates[2]["index"]
        idx_d = option_candidates[3]["index"]

        # Ensure options appear in top-down index order
        if not (idx_a < idx_b < idx_c < idx_d):
            raise QuestionNotFoundError("Option markers appear out of order on screen.")

        # 1. Question Text: Lines preceding Option A (filtering out top UI noise)
        question_lines: list[str] = []
        for line in lines[:idx_a]:
            line_text = _get_line_text(line)
            if TOP_NOISE_REGEX.search(line_text):
                logger.debug("Filtered top noise line: '%s'", line_text)
                continue
            question_lines.append(line_text)

        question_text = " ".join(question_lines).strip()
        if not question_text:
            raise QuestionNotFoundError("No question stem found above Option A.")

        # 2. Extract Option Texts and Bounding Boxes
        options: dict[str, str] = {}
        option_boxes: dict[str, BoundingBox] = {}

        # Option A
        opt_a_parts = [option_candidates[0]["initial_text"]] if option_candidates[0]["initial_text"] else []
        opt_a_boxes = [_get_line_box(lines[idx_a])]
        for line in lines[idx_a + 1 : idx_b]:
            opt_a_parts.append(_get_line_text(line))
            opt_a_boxes.append(_get_line_box(line))
        options["A"] = " ".join(opt_a_parts).strip()
        option_boxes["A"] = _compute_bounding_box_union(opt_a_boxes)

        # Option B
        opt_b_parts = [option_candidates[1]["initial_text"]] if option_candidates[1]["initial_text"] else []
        opt_b_boxes = [_get_line_box(lines[idx_b])]
        for line in lines[idx_b + 1 : idx_c]:
            opt_b_parts.append(_get_line_text(line))
            opt_b_boxes.append(_get_line_box(line))
        options["B"] = " ".join(opt_b_parts).strip()
        option_boxes["B"] = _compute_bounding_box_union(opt_b_boxes)

        # Option C
        opt_c_parts = [option_candidates[2]["initial_text"]] if option_candidates[2]["initial_text"] else []
        opt_c_boxes = [_get_line_box(lines[idx_c])]
        for line in lines[idx_c + 1 : idx_d]:
            opt_c_parts.append(_get_line_text(line))
            opt_c_boxes.append(_get_line_box(line))
        options["C"] = " ".join(opt_c_parts).strip()
        option_boxes["C"] = _compute_bounding_box_union(opt_c_boxes)

        # Option D
        opt_d_parts = [option_candidates[3]["initial_text"]] if option_candidates[3]["initial_text"] else []
        opt_d_boxes = [_get_line_box(lines[idx_d])]
        for line in lines[idx_d + 1 :]:
            line_text = _get_line_text(line)
            if BOTTOM_NOISE_REGEX.search(line_text):
                logger.debug("Filtered bottom noise line: '%s'", line_text)
                break
            opt_d_parts.append(line_text)
            opt_d_boxes.append(_get_line_box(line))
        options["D"] = " ".join(opt_d_parts).strip()
        option_boxes["D"] = _compute_bounding_box_union(opt_d_boxes)

        # Validate that option texts are non-empty
        for letter in ["A", "B", "C", "D"]:
            if not options[letter]:
                raise QuestionNotFoundError(f"Option {letter} text is empty.")

        raw_full_text = "\n".join(_get_line_text(line) for line in lines)

        return ParsedQuestion(
            question=question_text,
            options=options,
            option_boxes=option_boxes,
            raw_text=raw_full_text,
        )
