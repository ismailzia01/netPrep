"""macOS screen capture engine and Retina coordinate conversion utilities for netPrep."""

from __future__ import annotations

import ctypes
import logging
import os
import platform
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Any

from netprep.scan_pipeline import BoundingBox, ScreenCapturer

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CapturedImage:
    """Represents a screen capture with raw image bytes and Retina geometry."""

    png_bytes: bytes
    width_px: int
    height_px: int
    scale_factor: float
    origin_points: tuple[float, float] = (0.0, 0.0)

    @property
    def width_points(self) -> float:
        """Width in macOS screen points."""
        return self.width_px / self.scale_factor if self.scale_factor > 0 else float(self.width_px)

    @property
    def height_points(self) -> float:
        """Height in macOS screen points."""
        return self.height_px / self.scale_factor if self.scale_factor > 0 else float(self.height_px)


class ScreenRecordingPermissionError(PermissionError):
    """Raised when macOS Screen Recording permission has not been granted."""

    def __init__(self, message: str | None = None) -> None:
        default_message = (
            "macOS Screen Recording permission is not granted.\n"
            "To grant permission:\n"
            "  1. Open System Settings.\n"
            "  2. Navigate to 'Privacy & Security' -> 'Screen Recording'.\n"
            "  3. Toggle ON permission for your terminal application (or Python).\n"
            "  4. Restart netPrep."
        )
        super().__init__(message or default_message)


def check_screen_recording_permission() -> bool:
    """Check if the current process has macOS Screen Recording permission."""
    if platform.system() != "Darwin":
        return True

    try:
        core_graphics = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
        )
        if hasattr(core_graphics, "CGPreflightScreenCaptureAccess"):
            cg_preflight = core_graphics.CGPreflightScreenCaptureAccess
            cg_preflight.restype = ctypes.c_bool
            return bool(cg_preflight())
    except Exception as exc:
        logger.debug("Error checking CGPreflightScreenCaptureAccess: %s", exc)

    return False


# --- Coordinate Conversion Functions ---


def pixel_to_screen_point(
    px_x: float,
    px_y: float,
    scale_factor: float,
    origin_points: tuple[float, float] = (0.0, 0.0),
) -> tuple[float, float]:
    """Convert pixel coordinates to macOS screen point coordinates."""
    if scale_factor <= 0:
        raise ValueError(f"scale_factor must be positive, got {scale_factor}")
    screen_x = origin_points[0] + (px_x / scale_factor)
    screen_y = origin_points[1] + (px_y / scale_factor)
    return (screen_x, screen_y)


def screen_to_pixel_point(
    screen_x: float,
    screen_y: float,
    scale_factor: float,
    origin_points: tuple[float, float] = (0.0, 0.0),
) -> tuple[float, float]:
    """Convert macOS screen point coordinates to pixel coordinates."""
    if scale_factor <= 0:
        raise ValueError(f"scale_factor must be positive, got {scale_factor}")
    px_x = (screen_x - origin_points[0]) * scale_factor
    px_y = (screen_y - origin_points[1]) * scale_factor
    return (px_x, px_y)


def pixel_box_to_screen_box(
    box: BoundingBox,
    scale_factor: float,
    origin_points: tuple[float, float] = (0.0, 0.0),
) -> BoundingBox:
    """Convert a bounding box from pixel coordinates to macOS screen point coordinates."""
    screen_x, screen_y = pixel_to_screen_point(box.x, box.y, scale_factor, origin_points)
    screen_w = box.width / scale_factor
    screen_h = box.height / scale_factor
    return BoundingBox(
        x=int(round(screen_x)),
        y=int(round(screen_y)),
        width=int(round(screen_w)),
        height=int(round(screen_h)),
    )


def screen_box_to_pixel_box(
    box: BoundingBox,
    scale_factor: float,
    origin_points: tuple[float, float] = (0.0, 0.0),
) -> BoundingBox:
    """Convert a bounding box from macOS screen points to pixel coordinates."""
    px_x, px_y = screen_to_pixel_point(box.x, box.y, scale_factor, origin_points)
    px_w = box.width * scale_factor
    px_h = box.height * scale_factor
    return BoundingBox(
        x=int(round(px_x)),
        y=int(round(px_y)),
        width=int(round(px_w)),
        height=int(round(px_h)),
    )


def region_points_to_pixels(
    region: tuple[int, int, int, int],
    scale_factor: float,
) -> tuple[int, int, int, int]:
    """Convert a region (x, y, width, height) in screen points to pixels."""
    if scale_factor <= 0:
        raise ValueError(f"scale_factor must be positive, got {scale_factor}")
    rx, ry, rw, rh = region
    return (
        int(round(rx * scale_factor)),
        int(round(ry * scale_factor)),
        int(round(rw * scale_factor)),
        int(round(rh * scale_factor)),
    )


def get_screen_backing_scale_factor() -> float | None:
    """Return NSScreen.mainScreen().backingScaleFactor() if available."""
    try:
        from AppKit import NSScreen

        main_screen = NSScreen.mainScreen()
        if main_screen is not None:
            return float(main_screen.backingScaleFactor())
    except Exception as exc:
        logger.debug("Failed to query NSScreen backingScaleFactor: %s", exc)
    return None


def get_main_display_bounds() -> tuple[float, float, float, float]:
    """Determine main display bounds in screen points (origin_x, origin_y, width, height)."""
    origin_x, origin_y, width_pt, height_pt = 0.0, 0.0, 0.0, 0.0

    try:
        import Quartz

        display_id = Quartz.CGMainDisplayID()
        display_bounds = Quartz.CGDisplayBounds(display_id)
        origin_x = float(display_bounds.origin.x)
        origin_y = float(display_bounds.origin.y)
        width_pt = float(display_bounds.size.width)
        height_pt = float(display_bounds.size.height)
    except Exception as exc:
        logger.debug("Failed to query Quartz display bounds: %s", exc)

    if width_pt <= 0 or height_pt <= 0:
        try:
            from AppKit import NSScreen

            main_screen = NSScreen.mainScreen()
            if main_screen is not None:
                frame = main_screen.frame()
                origin_x = float(frame.origin.x)
                origin_y = float(frame.origin.y)
                width_pt = float(frame.size.width)
                height_pt = float(frame.size.height)
        except Exception as exc:
            logger.debug("Failed to query NSScreen frame: %s", exc)

    return (origin_x, origin_y, width_pt, height_pt)


# --- Capture Implementations ---


def _cgimage_to_png_bytes(cg_image: Any) -> bytes:
    """Serialize a CGImageRef into in-memory PNG bytes using ImageIO."""
    import Quartz
    from Foundation import NSMutableData

    data = NSMutableData.data()
    dest = Quartz.CGImageDestinationCreateWithData(data, "public.png", 1, None)
    if dest is None:
        raise RuntimeError("Failed to create CGImageDestination for PNG encoding.")

    Quartz.CGImageDestinationAddImage(dest, cg_image, None)
    success = Quartz.CGImageDestinationFinalize(dest)
    if not success:
        raise RuntimeError("Failed to finalize CGImageDestination encoding.")

    return bytes(data)


class QuartzScreenCapturer:
    """Captures macOS screen regions purely in-memory using CoreGraphics / Quartz."""

    def capture(
        self,
        region: tuple[int, int, int, int] | None = None,
    ) -> CapturedImage:
        """Capture screen or region in points (x, y, width, height) into a CapturedImage."""
        if not check_screen_recording_permission():
            raise ScreenRecordingPermissionError()

        import Quartz

        disp_x, disp_y, disp_w, disp_h = get_main_display_bounds()

        if region is not None:
            rx, ry, rw, rh = region
            target_rect = Quartz.CGRectMake(float(rx), float(ry), float(rw), float(rh))
            origin_points = (float(rx), float(ry))
            target_width_pt = float(rw)
        else:
            target_rect = Quartz.CGRectMake(disp_x, disp_y, disp_w, disp_h)
            origin_points = (disp_x, disp_y)
            target_width_pt = disp_w

        # Capture window list image for the target rectangle
        cg_image = Quartz.CGWindowListCreateImage(
            target_rect,
            Quartz.kCGWindowListOptionOnScreenOnly,
            Quartz.kCGNullWindowID,
            Quartz.kCGWindowImageDefault,
        )

        if cg_image is None:
            raise RuntimeError(
                "Quartz failed to capture screen image. "
                "Ensure display is active and screen recording permissions are enabled."
            )

        width_px = int(Quartz.CGImageGetWidth(cg_image))
        height_px = int(Quartz.CGImageGetHeight(cg_image))
        png_bytes = _cgimage_to_png_bytes(cg_image)

        scale_factor = float(width_px / target_width_pt) if target_width_pt > 0 else 1.0

        appkit_scale = get_screen_backing_scale_factor()
        if appkit_scale is not None and abs(scale_factor - appkit_scale) > 0.01:
            logger.warning(
                "Computed scale factor %.2f differs from NSScreen backingScaleFactor %.2f; using computed ratio.",
                scale_factor,
                appkit_scale,
            )

        return CapturedImage(
            png_bytes=png_bytes,
            width_px=width_px,
            height_px=height_px,
            scale_factor=scale_factor,
            origin_points=origin_points,
        )


class CliScreenCapturer:
    """Fallback capturer using macOS /usr/sbin/screencapture CLI with auto-cleaned tempfile."""

    def capture(
        self,
        region: tuple[int, int, int, int] | None = None,
    ) -> CapturedImage:
        """Capture screen via screencapture CLI with strict memory/temp cleanup."""
        if not check_screen_recording_permission():
            raise ScreenRecordingPermissionError()

        disp_x, disp_y, disp_w, disp_h = get_main_display_bounds()

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            cmd = ["/usr/sbin/screencapture", "-x"]
            if region is not None:
                rx, ry, rw, rh = region
                cmd.extend(["-R", f"{rx},{ry},{rw},{rh}"])
                origin_points = (float(rx), float(ry))
                target_width_pt = float(rw)
            else:
                origin_points = (disp_x, disp_y)
                target_width_pt = disp_w

            cmd.append(tmp_path)
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if res.returncode != 0:
                raise RuntimeError(
                    f"screencapture CLI failed with code {res.returncode}: {res.stderr.strip()}"
                )

            with open(tmp_path, "rb") as f:
                png_bytes = f.read()

            if not png_bytes:
                raise RuntimeError("screencapture CLI generated an empty file.")

            # Read dimensions from PNG header (IHDR chunk: bytes 16-24)
            width_px = int.from_bytes(png_bytes[16:20], byteorder="big")
            height_px = int.from_bytes(png_bytes[20:24], byteorder="big")

            scale_factor = float(width_px / target_width_pt) if target_width_pt > 0 else 1.0

            appkit_scale = get_screen_backing_scale_factor()
            if appkit_scale is not None and abs(scale_factor - appkit_scale) > 0.01:
                logger.warning(
                    "Computed scale factor %.2f differs from NSScreen backingScaleFactor %.2f; using computed ratio.",
                    scale_factor,
                    appkit_scale,
                )

            return CapturedImage(
                png_bytes=png_bytes,
                width_px=width_px,
                height_px=height_px,
                scale_factor=scale_factor,
                origin_points=origin_points,
            )
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass


class MacScreenCapturer(ScreenCapturer):
    """Primary macOS ScreenCapturer implementing the pipeline interface."""

    def __init__(self, region: tuple[int, int, int, int] | None = None) -> None:
        self.default_region = region
        self._quartz_capturer = QuartzScreenCapturer()
        self._cli_capturer = CliScreenCapturer()

    def capture(self, region: tuple[int, int, int, int] | None = None) -> CapturedImage:
        """Capture screen or region, raising ScreenRecordingPermissionError if untrusted."""
        target_region = region if region is not None else self.default_region

        try:
            return self._quartz_capturer.capture(region=target_region)
        except ScreenRecordingPermissionError:
            raise
        except Exception as exc:
            logger.debug("Quartz capture failed (%s); attempting CLI fallback...", exc)
            return self._cli_capturer.capture(region=target_region)
