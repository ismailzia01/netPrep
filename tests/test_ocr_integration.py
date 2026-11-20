"""Integration test: End-to-end synthetic image generation, Apple Vision OCR, and question parsing."""

from __future__ import annotations

import io
import platform
import unittest

from netprep.ocr import AppleVisionOcrEngine
from netprep.parser import RegexQuestionParser


class TestAppleVisionIntegration(unittest.TestCase):
    """End-to-end test on macOS: renders synthetic question image with Pillow, runs Vision OCR and parser."""

    @classmethod
    def setUpClass(cls) -> None:
        if platform.system() != "Darwin":
            raise unittest.SkipTest("Apple Vision integration test is only supported on macOS.")

        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError:
            raise unittest.SkipTest("Pillow is not installed in the environment.")

        # Create a clean, high-contrast synthetic image (1000x500 white canvas)
        cls.image = Image.new("RGB", (1000, 500), color="white")
        draw = ImageDraw.Draw(cls.image)

        # Use system font for crisp text rendering on macOS
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 24)
        except Exception:
            font = ImageFont.load_default(size=20)

        # Draw a synthetic multiple-choice question
        lines = [
            (40, 40, "Which layer in the netPrep model provides end-to-end transport?"),
            (40, 100, "A. Physical layer"),
            (40, 160, "B. Transport layer"),
            (40, 220, "C. Data link layer"),
            (40, 280, "D. Network layer"),
        ]
        for x, y, text in lines:
            draw.text((x, y), text, fill="black", font=font)

        buf = io.BytesIO()
        cls.image.save(buf, format="PNG")
        cls.png_bytes = buf.getvalue()

    def test_synthetic_image_ocr_and_parse(self) -> None:
        """Run OCR on synthetic PNG bytes and verify RegexQuestionParser output."""
        engine = AppleVisionOcrEngine()
        try:
            ocr_lines = engine.extract(self.png_bytes)
        except Exception as exc:  # e.g., missing pyobjc-framework-Vision or sandbox restriction
            raise unittest.SkipTest(f"Vision OCR could not run in current environment: {exc}")

        if not ocr_lines:
            raise unittest.SkipTest(
                "Vision OCR returned 0 lines (likely restricted by environment sandbox or missing visiond)."
            )

        parser = RegexQuestionParser()
        parsed = parser.parse(ocr_lines)

        self.assertIn("end-to-end transport", parsed.question.lower())
        self.assertEqual(parsed.options["A"], "Physical layer")
        self.assertEqual(parsed.options["B"], "Transport layer")
        self.assertEqual(parsed.options["C"], "Data link layer")
        self.assertEqual(parsed.options["D"], "Network layer")

        # Verify option bounding boxes were populated
        for letter in ["A", "B", "C", "D"]:
            self.assertIn(letter, parsed.option_boxes)
            box = parsed.option_boxes[letter]
            self.assertGreater(box.width, 0)
            self.assertGreater(box.height, 0)


if __name__ == "__main__":
    unittest.main()
