"""Unit tests for netprep.overlay (PySide6OverlayRenderer, OverlayWindow, coordinates, sequence)."""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, call, patch

# Ensure Qt runs offscreen for CI / headless testing
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication

from netprep.capture import pixel_box_to_screen_box
from netprep.config import AppConfig
from netprep.ocr import OcrLine
from netprep.overlay import OverlayWindow, PySide6OverlayRenderer
from netprep.parser import QuestionNotFoundError
from netprep.scan_pipeline import BoundingBox, ParsedQuestion


class TestOverlayCoordinatesAndPlacement(unittest.TestCase):
    """Test coordinate mapping (Retina scale, origin offset) and badge positioning."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication(["-platform", "offscreen"])

    def setUp(self) -> None:
        self.config = AppConfig(overlay_duration=4.0)
        self.window = OverlayWindow(self.config)
        # Mock window geometry for deterministic geometry tests (1920x1080)
        self.window.setGeometry(0, 0, 1920, 1080)

    def tearDown(self) -> None:
        self.window.hide_overlay()

    def test_retina_coordinate_conversion(self) -> None:
        """Verify pixel_box_to_screen_box scales dimensions and shifts origin correctly."""
        pixel_box = BoundingBox(x=200, y=400, width=800, height=80)
        screen_box = pixel_box_to_screen_box(
            box=pixel_box,
            scale_factor=2.0,
            origin_points=(50.0, 30.0),
        )
        self.assertEqual(screen_box.x, 150)
        self.assertEqual(screen_box.y, 230)
        self.assertEqual(screen_box.width, 400)
        self.assertEqual(screen_box.height, 40)

    def test_retina_option_box_overlay_placement(self) -> None:
        """OCR option box at (400, 640, 600, 60) px must produce (200, 320, 300, 30) pt."""
        ocr_pixel_box = BoundingBox(x=400, y=640, width=600, height=60)
        screen_box = pixel_box_to_screen_box(
            box=ocr_pixel_box,
            scale_factor=2.0,
            origin_points=(0.0, 0.0),
        )
        self.assertEqual(screen_box, BoundingBox(x=200, y=320, width=300, height=30))

        # Show on overlay window and verify geometry
        self.window.show_answer_marker("A", screen_box)
        self.assertEqual(self.window._highlight_rect.x(), 200)
        self.assertEqual(self.window._highlight_rect.y(), 320)
        self.assertEqual(self.window._highlight_rect.width(), 300)
        self.assertEqual(self.window._highlight_rect.height(), 30)
        self.assertEqual(self.window._badge_rect.x(), 160)  # 200 - 32 - 8

    def test_normal_answer_marker_and_badge_placement(self) -> None:
        """Verify normal answer marker sets highlight rect and positions badge next to option."""
        box = BoundingBox(x=200, y=300, width=500, height=40)
        self.window.show_answer_marker("B", box, duration=3.0)

        self.assertEqual(self.window._mode, "answer")
        self.assertEqual(self.window._answer_letter, "B")
        self.assertFalse(self.window._is_fallback_badge)
        self.assertIsNotNone(self.window._highlight_rect)
        self.assertIsNotNone(self.window._badge_rect)

        # Highlight box coordinates match screen box
        self.assertEqual(self.window._highlight_rect.x(), 200)
        self.assertEqual(self.window._highlight_rect.y(), 300)

        # Badge is placed immediately to the left of highlight rect
        # badge_x = 200 - 32 - 8 = 160
        self.assertEqual(self.window._badge_rect.x(), 160)
        self.assertEqual(self.window._badge_rect.width(), 32)
        self.assertEqual(self.window._badge_rect.height(), 32)

    def test_fallback_badge_when_box_is_missing(self) -> None:
        """When bounding box is None or empty, render fallback badge at top-center."""
        self.window.show_answer_marker("C", None, duration=3.0)

        self.assertEqual(self.window._mode, "answer")
        self.assertEqual(self.window._answer_letter, "C")
        self.assertTrue(self.window._is_fallback_badge)
        self.assertIsNone(self.window._highlight_rect)
        self.assertIsNotNone(self.window._badge_rect)

        # Centered at top of screen
        self.assertEqual(self.window._badge_rect.y(), 60)
        expected_x = (self.window.rect().width() - 260) // 2
        self.assertEqual(self.window._badge_rect.x(), expected_x)

    def test_timeout_and_dismissal(self) -> None:
        """Verify dismissal timer duration and hide_overlay state reset."""
        box = BoundingBox(x=100, y=200, width=300, height=30)
        self.window.show_answer_marker("A", box, duration=2.5)

        self.assertTrue(self.window._dismiss_timer.isActive())
        self.assertEqual(self.window._dismiss_timer.interval(), 2500)

        # Trigger timer expiration
        self.window.hide_overlay()
        self.assertFalse(self.window._dismiss_timer.isActive())
        self.assertIsNone(self.window._mode)
        self.assertIsNone(self.window._highlight_rect)

    def test_toast_message_mode(self) -> None:
        """Verify show_toast_message sets message mode and formats toast banner."""
        self.window.show_toast_message("No question found on screen", duration=2.0)

        self.assertEqual(self.window._mode, "message")
        self.assertEqual(self.window._message_text, "No question found on screen")
        self.assertIsNotNone(self.window._message_rect)
        self.assertEqual(self.window._message_rect.y(), 60)
        self.assertIsNone(self.window._highlight_rect)


class TestPySide6OverlayRendererThreadSafe(unittest.TestCase):
    """Test high-level PySide6OverlayRenderer dispatching and properties."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication(["-platform", "offscreen"])

    def setUp(self) -> None:
        self.config = AppConfig(overlay_duration=3.0)
        self.renderer = PySide6OverlayRenderer(self.config)

    def tearDown(self) -> None:
        self.renderer.hide()
        QApplication.processEvents()

    def test_show_answer_and_hide(self) -> None:
        question = ParsedQuestion(
            question="What is 2+2?",
            options={"A": "1", "B": "4", "C": "5", "D": "6"},
            option_boxes={"B": BoundingBox(x=100, y=200, width=300, height=30)},
        )
        self.renderer.show_answer("B", question)
        QApplication.processEvents()

        self.assertTrue(self.renderer.is_visible)

        self.renderer.hide()
        QApplication.processEvents()
        self.assertFalse(self.renderer.is_visible)

    def test_show_message(self) -> None:
        self.renderer.show_message("Test notification banner")
        QApplication.processEvents()

        self.assertTrue(self.renderer.is_visible)
        window = self.renderer._ensure_window()
        self.assertEqual(window._mode, "message")
        self.assertEqual(window._message_text, "Test notification banner")


class TestScanCycleSequenceOrder(unittest.TestCase):
    """Test strict sequence order: clear overlay -> capture -> OCR -> parse -> answer -> show overlay."""

    def test_clear_before_capture_order(self) -> None:
        from netprep.app import NetPrepApp

        # Mock all pipeline components to record method call sequence
        mock_capturer = MagicMock()
        mock_ocr = MagicMock()
        mock_parser = MagicMock()
        mock_answer_engine = MagicMock()
        mock_overlay = MagicMock()

        mock_capturer.capture.return_value = MagicMock()
        mock_ocr.extract.return_value = []
        dummy_q = ParsedQuestion(
            question="Sample Q",
            options={"A": "1", "B": "2", "C": "3", "D": "4"},
            option_boxes={},
        )
        mock_parser.parse.return_value = dummy_q
        mock_answer_engine.answer.return_value = "B"

        app = NetPrepApp(AppConfig(model_name="dummy"))
        app.capturer = mock_capturer
        app.ocr_engine = mock_ocr
        app.parser = mock_parser
        app.answer_engine = mock_answer_engine
        app.overlay = mock_overlay

        # Run scan cycle synchronously
        app.run_scan_cycle(synchronous=True)

        # Assert clear overlay (hide) is called first, before capture
        mock_overlay.hide.assert_called()
        mock_capturer.capture.assert_called_once()
        mock_ocr.extract.assert_called_once()
        mock_parser.parse.assert_called_once()
        mock_answer_engine.answer.assert_called_once()
        mock_overlay.show_answer.assert_called_once_with("B", dummy_q)

    def test_error_message_path_on_scan_failure(self) -> None:
        from netprep.app import NetPrepApp

        mock_capturer = MagicMock()
        mock_ocr = MagicMock()
        mock_parser = MagicMock()
        mock_overlay = MagicMock()

        mock_capturer.capture.return_value = MagicMock()
        mock_ocr.extract.return_value = []
        # Parser raises QuestionNotFoundError
        mock_parser.parse.side_effect = QuestionNotFoundError("No option markers found")

        app = NetPrepApp(AppConfig(model_name="dummy"))
        app.capturer = mock_capturer
        app.ocr_engine = mock_ocr
        app.parser = mock_parser
        app.overlay = mock_overlay

        app.run_scan_cycle(synchronous=True)

        # Verify show_message was called on overlay with error text
        mock_overlay.show_message.assert_called_once_with("No question found on screen")


if __name__ == "__main__":
    unittest.main()
