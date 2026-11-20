"""Unit tests for screen capture, Retina coordinate conversions, and permission handling."""

import unittest
from unittest.mock import MagicMock, patch

from netprep.capture import (
    CapturedImage,
    MacScreenCapturer,
    QuartzScreenCapturer,
    ScreenRecordingPermissionError,
    check_screen_recording_permission,
    get_main_display_bounds,
    get_screen_backing_scale_factor,
    pixel_box_to_screen_box,
    pixel_to_screen_point,
    region_points_to_pixels,
    screen_box_to_pixel_box,
    screen_to_pixel_point,
)
from netprep.config import AppConfig
from netprep.scan_pipeline import BoundingBox


class TestCoordinateConversion(unittest.TestCase):
    def test_pixel_to_screen_point_standard_scale(self) -> None:
        pt = pixel_to_screen_point(100.0, 200.0, scale_factor=1.0)
        self.assertEqual(pt, (100.0, 200.0))

    def test_pixel_to_screen_point_retina_scale(self) -> None:
        # On a 2x Retina display, 200px = 100pt
        pt = pixel_to_screen_point(200.0, 400.0, scale_factor=2.0)
        self.assertEqual(pt, (100.0, 200.0))

        # On a 3x Retina display, 300px = 100pt
        pt_3x = pixel_to_screen_point(300.0, 600.0, scale_factor=3.0)
        self.assertEqual(pt_3x, (100.0, 200.0))

    def test_pixel_to_screen_point_with_origin_offset(self) -> None:
        # Sub-region capture starting at (50, 100) screen points
        pt = pixel_to_screen_point(
            200.0, 400.0, scale_factor=2.0, origin_points=(50.0, 100.0)
        )
        self.assertEqual(pt, (150.0, 300.0))

    def test_screen_to_pixel_point_roundtrip(self) -> None:
        orig_screen = (150.0, 250.0)
        scale = 2.0
        origin = (20.0, 40.0)

        # Screen -> Pixel
        px_x, px_y = screen_to_pixel_point(
            orig_screen[0], orig_screen[1], scale_factor=scale, origin_points=origin
        )
        self.assertEqual(px_x, (150.0 - 20.0) * 2.0)
        self.assertEqual(px_y, (250.0 - 40.0) * 2.0)

        # Pixel -> Screen (roundtrip)
        res_screen = pixel_to_screen_point(
            px_x, px_y, scale_factor=scale, origin_points=origin
        )
        self.assertAlmostEqual(res_screen[0], orig_screen[0])
        self.assertAlmostEqual(res_screen[1], orig_screen[1])

    def test_invalid_scale_factor_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            pixel_to_screen_point(100.0, 100.0, scale_factor=0.0)
        with self.assertRaises(ValueError):
            screen_to_pixel_point(100.0, 100.0, scale_factor=-1.0)

    def test_bounding_box_conversions(self) -> None:
        # Pixel box: 200x400 at (100, 200) on 2x display
        px_box = BoundingBox(x=100, y=200, width=200, height=400)
        screen_box = pixel_box_to_screen_box(px_box, scale_factor=2.0)

        self.assertEqual(screen_box.x, 50)
        self.assertEqual(screen_box.y, 100)
        self.assertEqual(screen_box.width, 100)
        self.assertEqual(screen_box.height, 200)

        # Roundtrip back to pixel box
        back_px = screen_box_to_pixel_box(screen_box, scale_factor=2.0)
        self.assertEqual(back_px.x, 100)
        self.assertEqual(back_px.y, 200)
        self.assertEqual(back_px.width, 200)
        self.assertEqual(back_px.height, 400)

    def test_overlay_placement_retina_values(self) -> None:
        """OCR option box at (400, 640, 600, 60) px must produce (200, 320, 300, 30) pt."""
        ocr_pixel_box = BoundingBox(x=400, y=640, width=600, height=60)
        screen_box = pixel_box_to_screen_box(ocr_pixel_box, scale_factor=2.0, origin_points=(0.0, 0.0))

        self.assertEqual(screen_box.x, 200)
        self.assertEqual(screen_box.y, 320)
        self.assertEqual(screen_box.width, 300)
        self.assertEqual(screen_box.height, 30)

        # Region with non-zero origin (50.0, 100.0)
        screen_box_offset = pixel_box_to_screen_box(ocr_pixel_box, scale_factor=2.0, origin_points=(50.0, 100.0))
        self.assertEqual(screen_box_offset.x, 250)
        self.assertEqual(screen_box_offset.y, 420)
        self.assertEqual(screen_box_offset.width, 300)
        self.assertEqual(screen_box_offset.height, 30)


class TestCapturedImageDataclass(unittest.TestCase):
    def test_captured_image_dimensions_and_properties(self) -> None:
        img = CapturedImage(
            png_bytes=b"dummy_png_bytes",
            width_px=2880,
            height_px=1800,
            scale_factor=2.0,
            origin_points=(0.0, 0.0),
        )
        self.assertEqual(img.width_px, 2880)
        self.assertEqual(img.height_px, 1800)
        self.assertEqual(img.scale_factor, 2.0)
        self.assertEqual(img.width_points, 1440.0)
        self.assertEqual(img.height_points, 900.0)
        self.assertEqual(img.origin_points, (0.0, 0.0))


class TestCapturePermissionsAndConfig(unittest.TestCase):
    @patch("netprep.capture.check_screen_recording_permission", return_value=False)
    def test_permission_error_raised_when_untrusted(self, mock_check: MagicMock) -> None:
        capturer = MacScreenCapturer()
        with self.assertRaises(ScreenRecordingPermissionError) as ctx:
            capturer.capture()

        err_msg = str(ctx.exception)
        self.assertIn("Screen Recording", err_msg)
        self.assertIn("System Settings", err_msg)

    def test_config_capture_region_defaults(self) -> None:
        cfg = AppConfig()
        self.assertIsNone(cfg.capture_region)

    def test_config_capture_region_custom_serialization(self) -> None:
        cfg = AppConfig(capture_region=(10, 20, 800, 600))
        d = cfg.to_dict()
        self.assertEqual(d["capture_region"], (10, 20, 800, 600))

        reloaded = AppConfig.from_dict(d)
        self.assertEqual(reloaded.capture_region, (10, 20, 800, 600))

    def test_config_capture_region_malformed_falls_back(self) -> None:
        # Wrong length or type
        cfg1 = AppConfig.from_dict({"capture_region": [10, 20]})
        self.assertIsNone(cfg1.capture_region)

        cfg2 = AppConfig.from_dict({"capture_region": "invalid_string"})
        self.assertIsNone(cfg2.capture_region)


class TestMockQuartzCapture(unittest.TestCase):
    @patch("netprep.capture.check_screen_recording_permission", return_value=True)
    @patch("netprep.capture._cgimage_to_png_bytes", return_value=b"\x89PNG\r\n\x1a\nfake")
    def test_quartz_capture_returns_captured_image(
        self, mock_to_png: MagicMock, mock_perm: MagicMock
    ) -> None:
        capturer = QuartzScreenCapturer()

        mock_quartz = MagicMock()
        mock_quartz.CGMainDisplayID.return_value = 1
        mock_bounds = MagicMock()
        mock_bounds.origin.x = 0.0
        mock_bounds.origin.y = 0.0
        mock_bounds.size.width = 1440.0
        mock_bounds.size.height = 900.0
        mock_quartz.CGDisplayBounds.return_value = mock_bounds
        mock_quartz.CGDisplayPixelsWide.return_value = 2880
        mock_cg_image = MagicMock()
        mock_quartz.CGWindowListCreateImage.return_value = mock_cg_image
        mock_quartz.CGImageGetWidth.return_value = 2880
        mock_quartz.CGImageGetHeight.return_value = 1800

        with patch.dict("sys.modules", {"Quartz": mock_quartz}):
            result = capturer.capture()
            self.assertEqual(result.width_px, 2880)
            self.assertEqual(result.height_px, 1800)
            self.assertEqual(result.scale_factor, 2.0)
            self.assertEqual(result.png_bytes, b"\x89PNG\r\n\x1a\nfake")
            self.assertEqual(result.origin_points, (0.0, 0.0))

    @patch("netprep.capture.check_screen_recording_permission", return_value=True)
    @patch("netprep.capture._cgimage_to_png_bytes", return_value=b"\x89PNG\r\n\x1a\nfake")
    @patch("netprep.capture.get_screen_backing_scale_factor", return_value=2.0)
    def test_retina_macbook_capture_scale(
        self, mock_scale: MagicMock, mock_to_png: MagicMock, mock_perm: MagicMock
    ) -> None:
        """2940 x 1912 px with display 1470 x 956 pt -> scale 2.0."""
        capturer = QuartzScreenCapturer()

        mock_quartz = MagicMock()
        mock_quartz.CGMainDisplayID.return_value = 1
        mock_bounds = MagicMock()
        mock_bounds.origin.x = 0.0
        mock_bounds.origin.y = 0.0
        mock_bounds.size.width = 1470.0
        mock_bounds.size.height = 956.0
        mock_quartz.CGDisplayBounds.return_value = mock_bounds

        mock_cg_image = MagicMock()
        mock_quartz.CGWindowListCreateImage.return_value = mock_cg_image
        mock_quartz.CGImageGetWidth.return_value = 2940
        mock_quartz.CGImageGetHeight.return_value = 1912

        with patch.dict("sys.modules", {"Quartz": mock_quartz}):
            result = capturer.capture()
            self.assertEqual(result.width_px, 2940)
            self.assertEqual(result.height_px, 1912)
            self.assertEqual(result.scale_factor, 2.0)
            self.assertEqual(result.width_points, 1470.0)
            self.assertEqual(result.height_points, 956.0)
            self.assertEqual(result.origin_points, (0.0, 0.0))

    @patch("netprep.capture.check_screen_recording_permission", return_value=True)
    @patch("netprep.capture._cgimage_to_png_bytes", return_value=b"\x89PNG\r\n\x1a\nfake")
    @patch("netprep.capture.get_screen_backing_scale_factor", return_value=2.0)
    def test_retina_region_capture_with_non_zero_origin(
        self, mock_scale: MagicMock, mock_to_png: MagicMock, mock_perm: MagicMock
    ) -> None:
        """Region capture with non-zero origin converts region to pixels using scale 2.0."""
        capturer = QuartzScreenCapturer()

        mock_quartz = MagicMock()
        mock_quartz.CGMainDisplayID.return_value = 1
        mock_bounds = MagicMock()
        mock_bounds.origin.x = 100.0
        mock_bounds.origin.y = 50.0
        mock_bounds.size.width = 1470.0
        mock_bounds.size.height = 956.0
        mock_quartz.CGDisplayBounds.return_value = mock_bounds

        # Target region in screen points: (150, 80, 500, 300)
        # Using scale 2.0, pixel dimensions are 1000 x 600
        region_pts = (150, 80, 500, 300)
        expected_px = region_points_to_pixels(region_pts, scale_factor=2.0)
        self.assertEqual(expected_px, (300, 160, 1000, 600))

        mock_cg_image = MagicMock()
        mock_quartz.CGWindowListCreateImage.return_value = mock_cg_image
        mock_quartz.CGImageGetWidth.return_value = 1000
        mock_quartz.CGImageGetHeight.return_value = 600

        with patch.dict("sys.modules", {"Quartz": mock_quartz}):
            result = capturer.capture(region=region_pts)
            self.assertEqual(result.width_px, 1000)
            self.assertEqual(result.height_px, 600)
            self.assertEqual(result.scale_factor, 2.0)
            self.assertEqual(result.width_points, 500.0)
            self.assertEqual(result.height_points, 300.0)
            self.assertEqual(result.origin_points, (150.0, 80.0))

    @patch("netprep.capture.check_screen_recording_permission", return_value=True)
    @patch("netprep.capture._cgimage_to_png_bytes", return_value=b"\x89PNG\r\n\x1a\nfake")
    @patch("netprep.capture.get_screen_backing_scale_factor", return_value=1.0)
    def test_standard_1x_display_scale(
        self, mock_scale: MagicMock, mock_to_png: MagicMock, mock_perm: MagicMock
    ) -> None:
        """A 1x display (1920 x 1080 px, 1920 x 1080 pt) -> scale 1.0."""
        capturer = QuartzScreenCapturer()

        mock_quartz = MagicMock()
        mock_quartz.CGMainDisplayID.return_value = 1
        mock_bounds = MagicMock()
        mock_bounds.origin.x = 0.0
        mock_bounds.origin.y = 0.0
        mock_bounds.size.width = 1920.0
        mock_bounds.size.height = 1080.0
        mock_quartz.CGDisplayBounds.return_value = mock_bounds

        mock_cg_image = MagicMock()
        mock_quartz.CGWindowListCreateImage.return_value = mock_cg_image
        mock_quartz.CGImageGetWidth.return_value = 1920
        mock_quartz.CGImageGetHeight.return_value = 1080

        with patch.dict("sys.modules", {"Quartz": mock_quartz}):
            result = capturer.capture()
            self.assertEqual(result.width_px, 1920)
            self.assertEqual(result.height_px, 1080)
            self.assertEqual(result.scale_factor, 1.0)
            self.assertEqual(result.width_points, 1920.0)
            self.assertEqual(result.height_points, 1080.0)
            self.assertEqual(result.origin_points, (0.0, 0.0))

    @patch("netprep.capture.check_screen_recording_permission", return_value=True)
    @patch("netprep.capture._cgimage_to_png_bytes", return_value=b"\x89PNG\r\n\x1a\nfake")
    @patch("netprep.capture.get_screen_backing_scale_factor", return_value=1.0)
    def test_backing_scale_mismatch_warning_and_ratio_preserved(
        self, mock_scale: MagicMock, mock_to_png: MagicMock, mock_perm: MagicMock
    ) -> None:
        """When AppKit backingScaleFactor differs from computed ratio, log warning and preserve ratio."""
        capturer = QuartzScreenCapturer()

        mock_quartz = MagicMock()
        mock_quartz.CGMainDisplayID.return_value = 1
        mock_bounds = MagicMock()
        mock_bounds.origin.x = 0.0
        mock_bounds.origin.y = 0.0
        mock_bounds.size.width = 1470.0
        mock_bounds.size.height = 956.0
        mock_quartz.CGDisplayBounds.return_value = mock_bounds

        mock_cg_image = MagicMock()
        mock_quartz.CGWindowListCreateImage.return_value = mock_cg_image
        mock_quartz.CGImageGetWidth.return_value = 2940
        mock_quartz.CGImageGetHeight.return_value = 1912

        with patch.dict("sys.modules", {"Quartz": mock_quartz}):
            with self.assertLogs("netprep.capture", level="WARNING") as cm:
                result = capturer.capture()
            self.assertEqual(result.scale_factor, 2.0)
            self.assertTrue(any("Computed scale factor 2.00 differs from NSScreen" in msg for msg in cm.output))


if __name__ == "__main__":
    unittest.main()
