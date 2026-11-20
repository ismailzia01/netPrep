"""Unit tests for netprep.ocr (coordinate conversion and Vision OCR engine)."""

from __future__ import annotations

import platform
import unittest
from unittest.mock import MagicMock, patch

from netprep.capture import CapturedImage
from netprep.ocr import AppleVisionOcrEngine, OcrLine, vision_box_to_pixel_box
from netprep.scan_pipeline import BoundingBox


class TestVisionCoordinateConversion(unittest.TestCase):
    """Test normalized bottom-left Vision coordinates to top-left pixel coordinates."""

    def test_bottom_left_vision_to_pixel(self) -> None:
        """A box at the bottom-left in Vision coords (y=0) should map to the bottom in pixels."""
        # Vision: x=0, y=0, w=0.5, h=0.1 on a 1000x1000 image
        # In pixel coords:
        # x_px = 0, w_px = 500
        # y_px = (1.0 - (0.0 + 0.1)) * 1000 = 900
        box = vision_box_to_pixel_box(
            norm_x=0.0,
            norm_y=0.0,
            norm_w=0.5,
            norm_h=0.1,
            width_px=1000,
            height_px=1000,
        )
        self.assertEqual(box.x, 0)
        self.assertEqual(box.y, 900)
        self.assertEqual(box.width, 500)
        self.assertEqual(box.height, 100)

    def test_top_left_vision_to_pixel(self) -> None:
        """A box at the top-left in Vision coords (y=0.9, h=0.1) should map to top (y=0) in pixels."""
        # Vision: x=0.0, y=0.9, w=0.5, h=0.1 on 1000x1000
        # y_px = (1.0 - (0.9 + 0.1)) * 1000 = 0
        box = vision_box_to_pixel_box(
            norm_x=0.0,
            norm_y=0.9,
            norm_w=0.5,
            norm_h=0.1,
            width_px=1000,
            height_px=1000,
        )
        self.assertEqual(box.x, 0)
        self.assertEqual(box.y, 0)
        self.assertEqual(box.width, 500)
        self.assertEqual(box.height, 100)

    def test_center_box_conversion(self) -> None:
        """A box in the exact vertical center should stay centered after the y-flip."""
        # Vision: x=0.25, y=0.45, w=0.5, h=0.1 on 1920x1080
        # y_px = (1.0 - (0.45 + 0.10)) * 1080 = 0.45 * 1080 = 486
        box = vision_box_to_pixel_box(
            norm_x=0.25,
            norm_y=0.45,
            norm_w=0.5,
            norm_h=0.1,
            width_px=1920,
            height_px=1080,
        )
        self.assertEqual(box.x, round(0.25 * 1920))
        self.assertEqual(box.y, 486)
        self.assertEqual(box.width, round(0.5 * 1920))
        self.assertEqual(box.height, 108)

    def test_clamping_negative_coordinates(self) -> None:
        """Any negative coordinates should be clamped to zero."""
        box = vision_box_to_pixel_box(
            norm_x=-0.1,
            norm_y=1.2,
            norm_w=-0.2,
            norm_h=-0.1,
            width_px=1000,
            height_px=1000,
        )
        self.assertEqual(box.x, 0)
        self.assertEqual(box.y, 0)
        self.assertEqual(box.width, 0)
        self.assertEqual(box.height, 0)


class TestAppleVisionOcrEngineMocked(unittest.TestCase):
    """Test AppleVisionOcrEngine with mocked PyObjC Vision framework components."""

    def setUp(self) -> None:
        self.engine = AppleVisionOcrEngine()

    def test_unsupported_image_type_raises_type_error(self) -> None:
        """Passing an invalid object type raises TypeError."""
        with self.assertRaises(TypeError):
            self.engine.extract(12345)  # type: ignore[arg-type]

    def test_dict_backward_compatibility(self) -> None:
        """Passing a legacy dictionary returns synthetic OCR line."""
        result = self.engine.extract({"text": "Sample question text", "width": 200})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].text, "Sample question text")
        self.assertEqual(result[0].confidence, 1.0)

    @patch("netprep.ocr.platform.system", return_value="Linux")
    def test_non_darwin_raises_runtime_error(self, _mock_platform: MagicMock) -> None:
        """Calling extract on a non-Darwin system raises RuntimeError."""
        engine = AppleVisionOcrEngine()
        with self.assertRaises(RuntimeError):
            engine.extract(b"dummy_bytes")

    def test_extract_mocked_vision_observations(self) -> None:
        """Mock Vision.VNRecognizeTextRequest and verify sorted OcrLine outputs."""
        captured_img = CapturedImage(
            png_bytes=b"\x89PNG\r\n\x1a\nfake",
            width_px=1000,
            height_px=1000,
            scale_factor=2.0,
            origin_points=(100.0, 50.0),
        )

        mock_vision = MagicMock()
        mock_foundation = MagicMock()

        # Observation 1: lower down the screen (higher pixel y)
        obs_lower = MagicMock()
        cand_lower = MagicMock()
        cand_lower.string.return_value = "B) Second line"
        cand_lower.confidence.return_value = 0.95
        obs_lower.topCandidates_.return_value = [cand_lower]
        obs_lower.boundingBox.return_value.origin.x = 0.1
        obs_lower.boundingBox.return_value.origin.y = 0.7  # pixel y = (1.0 - 0.75)*1000 = 250
        obs_lower.boundingBox.return_value.size.width = 0.8
        obs_lower.boundingBox.return_value.size.height = 0.05

        # Observation 2: higher up the screen (lower pixel y)
        obs_higher = MagicMock()
        cand_higher = MagicMock()
        cand_higher.string.return_value = "A) First line"
        cand_higher.confidence.return_value = 0.99
        obs_higher.topCandidates_.return_value = [cand_higher]
        obs_higher.boundingBox.return_value.origin.x = 0.1
        obs_higher.boundingBox.return_value.origin.y = 0.85  # pixel y = (1.0 - 0.90)*1000 = 100
        obs_higher.boundingBox.return_value.size.width = 0.8
        obs_higher.boundingBox.return_value.size.height = 0.05

        # Handler returns observations out of order
        mock_handler = MagicMock()
        mock_handler.performRequests_error_.return_value = (True, None)
        mock_vision.VNImageRequestHandler.alloc().initWithData_options_.return_value = mock_handler

        mock_req = MagicMock()
        mock_req.results.return_value = [obs_lower, obs_higher]
        mock_vision.VNRecognizeTextRequest.alloc().init.return_value = mock_req

        with patch.dict(
            "sys.modules",
            {"Vision": mock_vision, "Foundation": mock_foundation},
        ):
            lines = self.engine.extract(captured_img)

        self.assertEqual(len(lines), 2)
        # Should be sorted top-to-bottom: "A) First line" first (y=100), then "B) Second line" (y=250)
        self.assertEqual(lines[0].text, "A) First line")
        self.assertEqual(lines[0].box_px.y, 100)
        self.assertEqual(lines[1].text, "B) Second line")
        self.assertEqual(lines[1].box_px.y, 250)

        # Verify scale factor and screen points offset applied correctly
        # origin_points is (100.0, 50.0), scale_factor is 2.0
        # For first line: box_px.x = 100, box_px.y = 100 -> screen points = (100 + 100/2, 50 + 100/2) = (150, 100)
        self.assertEqual(lines[0].box_points.x, 150)
        self.assertEqual(lines[0].box_points.y, 100)


if __name__ == "__main__":
    unittest.main()
