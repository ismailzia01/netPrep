#!/usr/bin/env python3
"""Developer verification script for netPrep OCR and Question Parsing stages.

Runs Apple Vision OCR and RegexQuestionParser against an image file or live screen capture,
printing recognized lines, confidences, bounding boxes, and parsing metrics.
Memory-only by default; saves nothing to disk unless --out is explicitly passed.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Ensure workspace root is in sys.path
workspace_root = Path(__file__).resolve().parent.parent
if str(workspace_root) not in sys.path:
    sys.path.insert(0, str(workspace_root))

from PIL import Image

from netprep.capture import (
    CapturedImage,
    MacScreenCapturer,
    ScreenRecordingPermissionError,
    check_screen_recording_permission,
)
from netprep.ocr import AppleVisionOcrEngine
from netprep.parser import QuestionNotFoundError, RegexQuestionParser


def parse_region(region_str: str | None) -> tuple[int, int, int, int] | None:
    """Parse comma-separated 'x,y,w,h' string into integer tuple."""
    if not region_str:
        return None
    parts = [p.strip() for p in region_str.split(",")]
    if len(parts) != 4:
        raise ValueError(f"Region must be 'x,y,w,h' (4 numbers), got: {region_str}")
    return (int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]))


def main() -> None:
    """Run OCR and parser verification, printing output and timing statistics."""
    parser = argparse.ArgumentParser(
        description="Verify netPrep on-device OCR and question parsing pipeline."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--image", help="Path to input image file (PNG/JPEG).")
    group.add_argument("--live", action="store_true", help="Capture live screen region.")

    parser.add_argument(
        "--region",
        default=None,
        help="Optional screen region for live capture in points: 'x,y,width,height'",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Optional destination path to save the captured image. Default: in-memory only.",
    )
    args = parser.parse_args()

    captured_img: CapturedImage

    if args.image:
        image_path = Path(args.image).resolve()
        if not image_path.exists():
            sys.stderr.write(f"Error: Image not found at {image_path}\n")
            sys.exit(1)
        with Image.open(image_path) as pil_img:
            w_px, h_px = pil_img.size
        png_bytes = image_path.read_bytes()
        captured_img = CapturedImage(
            png_bytes=png_bytes,
            width_px=w_px,
            height_px=h_px,
            scale_factor=1.0,
            origin_points=(0.0, 0.0),
        )
    else:
        # Live capture
        if not check_screen_recording_permission():
            sys.stderr.write(
                "\n====================================================================\n"
                "ERROR: macOS Screen Recording permission is not granted.\n"
                "Cannot perform live screen capture for OCR.\n"
                "To enable: Open System Settings -> Privacy & Security -> Screen Recording.\n"
                "====================================================================\n\n"
            )
            sys.exit(1)

        try:
            region = parse_region(args.region)
        except ValueError as exc:
            sys.stderr.write(f"Invalid region format: {exc}\n")
            sys.exit(1)

        capturer = MacScreenCapturer(region=region)
        try:
            captured_img = capturer.capture(region=region)
        except ScreenRecordingPermissionError as perm_err:
            sys.stderr.write(f"Permission error: {perm_err}\n")
            sys.exit(1)

    if args.out:
        out_path = Path(args.out).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(captured_img.png_bytes)
        print(f"Saved input image to: {out_path}")

    # Run OCR stage
    ocr_engine = AppleVisionOcrEngine()
    t0 = time.perf_counter()
    ocr_lines = ocr_engine.extract(captured_img)
    t_ocr_ms = (time.perf_counter() - t0) * 1000.0

    print("\n" + "=" * 65)
    print(" netPrep OCR Recognized Lines")
    print("=" * 65)
    print(f" Total Lines Detected: {len(ocr_lines)}")
    print(f" OCR Latency         : {t_ocr_ms:.2f} ms")
    print("-" * 65)
    for idx, line in enumerate(ocr_lines, start=1):
        box = line.box_px
        print(f" [{idx:02d}] (conf: {line.confidence:.2f}) [px: x={box.x}, y={box.y}, w={box.width}, h={box.height}]")
        print(f"      \"{line.text}\"")
    print("=" * 65)

    # Run Parser stage
    question_parser = RegexQuestionParser()
    t1 = time.perf_counter()
    parsed_q = None
    parse_error = None
    try:
        parsed_q = question_parser.parse(ocr_lines)
    except QuestionNotFoundError as q_err:
        parse_error = q_err
    t_parse_ms = (time.perf_counter() - t1) * 1000.0

    print("\n" + "=" * 65)
    print(" netPrep Question Parsing Results")
    print("=" * 65)
    print(f" Parser Latency      : {t_parse_ms:.2f} ms")
    print(f" Total Pipeline Time : {t_ocr_ms + t_parse_ms:.2f} ms")
    print("-" * 65)

    if parse_error is not None:
        print(" STATUS: NO QUESTION FOUND")
        print(f" Reason: {parse_error}")
        print("=" * 65 + "\n")
        sys.exit(1)

    assert parsed_q is not None
    print(" STATUS: QUESTION FOUND")
    print(f" Question Text: \"{parsed_q.question}\"")
    print("\n Options:")
    for letter in ["A", "B", "C", "D"]:
        box = parsed_q.option_boxes.get(letter)
        box_str = f"box: (x={box.x}, y={box.y}, w={box.width}, h={box.height})" if box else "(no box)"
        print(f"   [{letter}] \"{parsed_q.options[letter]}\"  {box_str}")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
