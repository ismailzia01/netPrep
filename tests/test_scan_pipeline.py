"""Unit tests for scan pipeline interfaces, dataclasses, and stub implementations."""

import unittest

from netprep.scan_pipeline import (
    BoundingBox,
    DummyAnswerEngine,
    ParsedQuestion,
    StubOcrEngine,
    StubOverlayRenderer,
    StubQuestionParser,
    StubScreenCapturer,
)


class TestScanPipeline(unittest.TestCase):
    def test_bounding_box_and_parsed_question(self) -> None:
        box = BoundingBox(x=10, y=20, width=100, height=30)
        self.assertEqual(box.to_dict(), {"x": 10, "y": 20, "width": 100, "height": 30})

        question = ParsedQuestion(
            question="What is 2 + 2?",
            options={"A": "1", "B": "2", "C": "3", "D": "4"},
            option_boxes={"A": box, "B": box, "C": box, "D": box},
        )
        self.assertEqual(question.validate(), [])

    def test_parsed_question_validation_errors(self) -> None:
        bad_q = ParsedQuestion(
            question="",
            options={"A": "1", "B": "2"},
        )
        errors = bad_q.validate()
        self.assertEqual(len(errors), 2)
        self.assertTrue(any("empty" in e.lower() for e in errors))
        self.assertTrue(any("options must be exactly" in e.lower() for e in errors))

    def test_stubs_pipeline_flow(self) -> None:
        capturer = StubScreenCapturer()
        ocr = StubOcrEngine()
        parser = StubQuestionParser()
        engine = DummyAnswerEngine(default_answer="B")
        overlay = StubOverlayRenderer()

        # Step 1: Capture
        raw_img = capturer.capture()
        self.assertIn("width", raw_img)

        # Step 2: OCR
        extracted = ocr.extract(raw_img)
        self.assertIn("text", extracted)

        # Step 3: Parser
        parsed = parser.parse(extracted)
        self.assertEqual(len(parsed.options), 4)
        self.assertEqual(parsed.options["B"], "ARP")

        # Step 4: Answer Engine
        answer = engine.answer(parsed)
        self.assertEqual(answer, "B")
        self.assertEqual(engine.call_count, 1)

        # Step 5: Overlay
        self.assertFalse(overlay.is_visible)
        overlay.show_answer(answer, parsed)
        self.assertTrue(overlay.is_visible)
        self.assertEqual(overlay.last_answer, "B")
        overlay.hide()
        self.assertFalse(overlay.is_visible)


if __name__ == "__main__":
    unittest.main()
