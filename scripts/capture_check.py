#!/usr/bin/env python3
"""Developer verification script for netPrep screen capture.

Captures the screen once, prints capture metrics (dimensions, scale factor, duration),
and optionally saves the PNG output if an explicit destination is specified.
Default execution runs 100% in-memory with zero disk writes.
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

from netprep.capture import (
    MacScreenCapturer,
    ScreenRecordingPermissionError,
    check_screen_recording_permission,
)


def parse_region(region_str: str | None) -> tuple[int, int, int, int] | None:
    """Parse comma-separated 'x,y,w,h' string into integer tuple."""
    if not region_str:
        return None
    parts = [p.strip() for p in region_str.split(",")]
    if len(parts) != 4:
        raise ValueError(f"Region must be 'x,y,w,h' (4 numbers), got: {region_str}")
    return (int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]))


def main() -> None:
    """Run capture check, print metrics, and optionally write output PNG."""
    parser = argparse.ArgumentParser(
        description="Verify netPrep macOS screen capture and Retina geometry."
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Optional file path to save the captured PNG. Default: in-memory only (no disk write).",
    )
    parser.add_argument(
        "--region",
        default=None,
        help="Optional capture region in screen points: 'x,y,width,height'",
    )
    args = parser.parse_args()

    try:
        region = parse_region(args.region)
    except ValueError as exc:
        sys.stderr.write(f"Invalid region argument: {exc}\n")
        sys.exit(1)

    print("Checking macOS Screen Recording permission...")
    has_perm = check_screen_recording_permission()
    print(f"Screen Recording permission status: {'GRANTED' if has_perm else 'DENIED'}")

    capturer = MacScreenCapturer(region=region)

    start_time = time.perf_counter()
    try:
        captured = capturer.capture(region=region)
    except ScreenRecordingPermissionError as perm_err:
        sys.stderr.write("\n" + "=" * 65 + "\n")
        sys.stderr.write("ERROR: Screen Recording permission is not granted.\n")
        sys.stderr.write(f"{perm_err}\n")
        sys.stderr.write("=" * 65 + "\n\n")
        sys.exit(1)
    except Exception as exc:
        sys.stderr.write(f"\nCapture failed: {exc}\n")
        sys.exit(1)

    elapsed_ms = (time.perf_counter() - start_time) * 1000.0

    print("\n" + "=" * 55)
    print(" netPrep Screen Capture Verification")
    print("=" * 55)
    print(f" Pixel Dimensions  : {captured.width_px} x {captured.height_px} px")
    print(f" Point Dimensions  : {captured.width_points:.1f} x {captured.height_points:.1f} pt")
    print(f" Scale Factor      : {captured.scale_factor:.2f}x ({'Retina' if captured.scale_factor > 1 else 'Standard'})")
    print(f" Origin (Points)   : ({captured.origin_points[0]:.1f}, {captured.origin_points[1]:.1f})")
    print(f" PNG In-Memory Size: {len(captured.png_bytes) / 1024:.2f} KB ({len(captured.png_bytes)} bytes)")
    print(f" Capture Time Taken: {elapsed_ms:.2f} ms")
    print("=" * 55)

    if args.out:
        out_path = Path(args.out).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(captured.png_bytes)
        print(f"Saved capture to: {out_path}")
    else:
        print("Note: In-memory capture verified. (Pass --out <path> to save output PNG to disk).")


if __name__ == "__main__":
    main()
