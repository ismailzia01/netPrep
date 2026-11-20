"""Apple Vision OCR engine and coordinate transformation for netPrep."""

from __future__ import annotations

import logging
import platform
from dataclasses import dataclass
from typing import Any

from netprep.capture import CapturedImage, pixel_box_to_screen_box
from netprep.scan_pipeline import BoundingBox, OcrEngine

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OcrLine:
    """Represents a recognized text line with confidence and spatial bounding boxes."""

    text: str
    confidence: float
    box_px: BoundingBox
    box_points: BoundingBox


def vision_box_to_pixel_box(
    norm_x: float,
    norm_y: float,
    norm_w: float,
    norm_h: float,
    width_px: int,
    height_px: int,
) -> BoundingBox:
    """Convert Vision normalized coordinates (origin bottom-left [0,1]) to top-left pixel coordinates.

    In Apple's Vision framework:
      - norm_x: 0.0 is left, 1.0 is right
      - norm_y: 0.0 is bottom of image, 1.0 is top of image
      - norm_w, norm_h: dimensions relative to image width/height

    In top-left pixel coordinates:
      - x_px = round(norm_x * width_px)
      - y_px = round((1.0 - (norm_y + norm_h)) * height_px)
      - w_px = round(norm_w * width_px)
      - h_px = round(norm_h * height_px)
    """
    x_px = int(round(norm_x * width_px))
    y_px = int(round((1.0 - (norm_y + norm_h)) * height_px))
    w_px = int(round(norm_w * width_px))
    h_px = int(round(norm_h * height_px))

    # Clamp to valid non-negative coordinates
    return BoundingBox(
        x=max(0, x_px),
        y=max(0, y_px),
        width=max(0, w_px),
        height=max(0, h_px),
    )


class AppleVisionOcrEngine(OcrEngine):
    """On-device OCR engine using Apple's Vision framework (VNRecognizeTextRequest)."""

    def __init__(self) -> None:
        self._available = platform.system() == "Darwin"
        if not self._available:
            logger.warning("AppleVisionOcrEngine is only supported on macOS.")

    def extract(self, image: Any) -> list[OcrLine]:
        """Perform on-device text recognition on a CapturedImage or raw image bytes.

        Returns a list of OcrLine objects sorted vertically from top to bottom.
        """
        if not self._available:
            raise RuntimeError("Apple Vision framework is not available on this platform.")

        if isinstance(image, CapturedImage):
            png_bytes = image.png_bytes
            width_px = image.width_px
            height_px = image.height_px
            scale_factor = image.scale_factor
            origin_points = image.origin_points
        elif isinstance(image, (bytes, bytearray)):
            png_bytes = bytes(image)
            # Fallback dimensions from PNG header
            if len(png_bytes) >= 24 and png_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
                width_px = int.from_bytes(png_bytes[16:20], byteorder="big")
                height_px = int.from_bytes(png_bytes[20:24], byteorder="big")
            else:
                width_px = 1920
                height_px = 1080
            scale_factor = 2.0
            origin_points = (0.0, 0.0)
        elif isinstance(image, dict):
            # For backward compatibility with stubs
            return [
                OcrLine(
                    text=image.get("text", ""),
                    confidence=1.0,
                    box_px=BoundingBox(0, 0, image.get("width", 100), 20),
                    box_points=BoundingBox(0, 0, image.get("width", 100) // 2, 10),
                )
            ]
        else:
            raise TypeError(f"Unsupported image type for OCR extraction: {type(image)}")

        try:
            import Vision
            from Foundation import NSData, NSDictionary
        except ImportError as exc:
            raise RuntimeError(
                f"pyobjc-framework-Vision is required for AppleVisionOcrEngine: {exc}"
            ) from exc

        ns_data = NSData.dataWithBytes_length_(png_bytes, len(png_bytes))
        handler = Vision.VNImageRequestHandler.alloc().initWithData_options_(
            ns_data, NSDictionary.dictionary()
        )

        request = Vision.VNRecognizeTextRequest.alloc().init()
        request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
        request.setUsesLanguageCorrection_(True)

        success, error = handler.performRequests_error_([request], None)
        if not success or error is not None:
            err_msg = error.localizedDescription() if error else "Unknown error"
            logger.warning("Vision performRequests failed: %s", err_msg)
            return []

        results = request.results()
        if not results:
            logger.debug("Vision OCR returned 0 text lines.")
            return []

        ocr_lines: list[OcrLine] = []
        for observation in results:
            top_candidates = observation.topCandidates_(1)
            if not top_candidates:
                continue
            cand = top_candidates[0]
            text = str(cand.string()).strip()
            confidence = float(cand.confidence())
            norm_box = observation.boundingBox()

            box_px = vision_box_to_pixel_box(
                norm_x=float(norm_box.origin.x),
                norm_y=float(norm_box.origin.y),
                norm_w=float(norm_box.size.width),
                norm_h=float(norm_box.size.height),
                width_px=width_px,
                height_px=height_px,
            )

            box_points = pixel_box_to_screen_box(
                box=box_px,
                scale_factor=scale_factor,
                origin_points=origin_points,
            )

            ocr_lines.append(
                OcrLine(
                    text=text,
                    confidence=confidence,
                    box_px=box_px,
                    box_points=box_points,
                )
            )

        # Sort lines top-to-bottom by vertical pixel coordinate
        ocr_lines.sort(key=lambda line: (line.box_px.y, line.box_px.x))
        return ocr_lines
