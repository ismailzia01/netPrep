#!/usr/bin/env python3
"""Developer verification script for netPrep PySide6 overlay rendering.

Displays a test visual marker (highlight box + badge), a fallback badge,
or a sample error message toast for eye-level placement and appearance verification.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure workspace root is in sys.path
workspace_root = Path(__file__).resolve().parent.parent
if str(workspace_root) not in sys.path:
    sys.path.insert(0, str(workspace_root))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from netprep.config import load_config
from netprep.overlay import PySide6OverlayRenderer
from netprep.scan_pipeline import BoundingBox, ParsedQuestion


def parse_box(box_str: str | None) -> BoundingBox | None:
    """Parse 'x,y,w,h' string into a BoundingBox."""
    if not box_str:
        return None
    parts = [int(p.strip()) for p in box_str.split(",")]
    if len(parts) != 4:
        raise ValueError(f"Box must be 4 comma-separated integers 'x,y,w,h', got: {box_str}")
    return BoundingBox(x=parts[0], y=parts[1], width=parts[2], height=parts[3])


def main() -> None:
    """Run visual overlay demo."""
    parser = argparse.ArgumentParser(
        description="Verify netPrep visual overlay placement, badges, and error banners."
    )
    parser.add_argument(
        "--option",
        default="B",
        choices=["A", "B", "C", "D"],
        help="Answer option letter to highlight (default: B)",
    )
    parser.add_argument(
        "--box",
        default="200,320,520,40",
        help="Option bounding box in screen points 'x,y,width,height' (default: 200,320,520,40)",
    )
    parser.add_argument(
        "--fallback",
        action="store_true",
        help="Simulate missing/off-screen box (renders top-center fallback badge)",
    )
    parser.add_argument(
        "--error",
        default=None,
        help="Display sample error message banner instead of answer marker (e.g. 'No question found')",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=6.0,
        help="Duration in seconds before overlay automatically dismisses (default: 6.0)",
    )
    args = parser.parse_args()

    app = QApplication.instance() or QApplication(sys.argv)
    config = load_config()
    config.overlay_duration = args.duration

    renderer = PySide6OverlayRenderer(config=config)

    print("\n" + "=" * 65)
    print(" netPrep Overlay Visual Verification Demo")
    print("=" * 65)
    print(f" Display Duration : {args.duration:.1f} seconds")

    if args.error:
        print(f" Mode             : Error / Notification Toast")
        print(f" Message Text     : \"{args.error}\"")
        print("=" * 65 + "\n")
        renderer.show_message(args.error, duration=args.duration)
    elif args.fallback:
        print(f" Mode             : Fallback Answer Badge (No bounding box)")
        print(f" Answer Letter    : [{args.option}]")
        print(" Placement        : Top-center of primary screen")
        print("=" * 65 + "\n")
        dummy_q = ParsedQuestion(
            question="Demo question without coordinates?",
            options={"A": "1", "B": "2", "C": "3", "D": "4"},
            option_boxes={},
        )
        renderer.show_answer(args.option, dummy_q)
    else:
        box = parse_box(args.box)
        assert box is not None
        print(f" Mode             : Normal Answer Marker")
        print(f" Answer Letter    : [{args.option}]")
        print(f" Highlight Box    : x={box.x}, y={box.y}, w={box.width}, h={box.height}")
        print(" Badge Position   : Immediately left of option box (or inside top-left)")
        print("=" * 65 + "\n")

        dummy_q = ParsedQuestion(
            question="Which protocol provides connection-oriented reliable byte streams?",
            options={
                "A": "User Datagram Protocol (UDP)",
                "B": "Transmission Control Protocol (TCP)",
                "C": "Internet Protocol (IP)",
                "D": "Internet Control Message Protocol (ICMP)",
            },
            option_boxes={args.option: box},
        )
        renderer.show_answer(args.option, dummy_q)

    # Automatically quit application once duration expires plus a 500ms safety buffer
    QTimer.singleShot(int((args.duration + 0.5) * 1000), app.quit)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
