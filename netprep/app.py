"""Application entry point for netPrep."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from pathlib import Path

from netprep.config import AppConfig, load_config
from netprep.hotkey import HotkeyListener
from netprep.scan_pipeline import (
    DummyAnswerEngine,
    StubOcrEngine,
    StubOverlayRenderer,
    StubQuestionParser,
    StubScreenCapturer,
)
from netprep.subjects import get_subject_pack, list_subject_packs
from netprep.tray import NetPrepTray

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("netprep")

try:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    HAS_PYSIDE6 = True
except ImportError:
    HAS_PYSIDE6 = False


class NetPrepApp:
    """Coordinates menu-bar tray, hotkey listener, and scan pipeline."""

    def __init__(self, config: AppConfig | None = None) -> None:
        self.config = config or load_config()
        self.qapp = None
        self._running = False

        if HAS_PYSIDE6:
            self.qapp = QApplication.instance() or QApplication(sys.argv)
            self.qapp.setQuitOnLastWindowClosed(False)

        # Pipeline stubs
        self.capturer = StubScreenCapturer()
        self.ocr_engine = StubOcrEngine()
        self.parser = StubQuestionParser()
        self.answer_engine = DummyAnswerEngine()
        self.overlay = StubOverlayRenderer()

        # Hotkey listener
        self.hotkey = HotkeyListener(
            hotkey=self.config.hotkey,
            callback=self.run_scan_cycle,
        )

        # Tray UI
        self.tray = NetPrepTray(
            config=self.config,
            on_scan=self.run_scan_cycle,
            on_subject_changed=self.handle_subject_changed,
            on_pause_toggled=self.handle_pause_toggled,
            on_quit=self.quit,
        )

        self._signal_timer = None
        if HAS_PYSIDE6 and self.qapp:
            self._signal_timer = QTimer()
            self._signal_timer.timeout.connect(lambda: None)
            self._signal_timer.start(500)

    def run_scan_cycle(self) -> None:
        """Execute a full scan cycle through the pipeline."""
        logger.info("Starting scan cycle...")
        try:
            # 1. Screen capture
            image = self.capturer.capture()

            # 2. OCR text extraction
            ocr_data = self.ocr_engine.extract(image)

            # 3. Question parsing
            parsed_question = self.parser.parse(ocr_data)

            # 4. Resolve active subject pack
            subject_pack = get_subject_pack(self.config.active_subject, self.config.subjects_dir)

            # 5. Answer prediction
            answer_letter = self.answer_engine.answer(parsed_question, subject=subject_pack)

            # 6. Show overlay
            self.overlay.show_answer(answer_letter, parsed_question)
            logger.info("Scan completed successfully. Suggested Answer: [%s]", answer_letter)
        except Exception as exc:
            logger.error("Scan cycle encountered an error: %s", exc, exc_info=True)

    def handle_subject_changed(self, subject_id: str) -> None:
        """Respond to subject selection from tray."""
        self.config.active_subject = subject_id
        pack = get_subject_pack(subject_id, self.config.subjects_dir)
        name = pack.name if pack else subject_id
        logger.info("Active subject changed to: %s", name)

    def handle_pause_toggled(self, is_paused: bool) -> None:
        """Respond to hotkey pause toggle from tray."""
        if is_paused:
            self.hotkey.pause()
        else:
            self.hotkey.resume()

    def start(self, run_seconds: float | None = None, trigger_scan: bool = False) -> int:
        """Start the application, show tray icon, and enter event loop."""
        logger.info("Starting netPrep...")
        logger.info("Configured hotkey: %s", self.config.hotkey)
        logger.info("Active subject: %s", self.config.active_subject)

        discovered = list_subject_packs(self.config.subjects_dir)
        logger.info(
            "Found %d subject pack(s): %s",
            len(discovered),
            [p.name for p in discovered],
        )

        self._running = True
        self.tray.show()
        self.hotkey.start()

        # Handle SIGINT cleanly
        signal.signal(signal.SIGINT, lambda *_: self.quit())
        signal.signal(signal.SIGTERM, lambda *_: self.quit())

        if trigger_scan:
            self.hotkey.trigger_manually()

        if run_seconds is not None:
            if HAS_PYSIDE6 and self.qapp:
                QTimer.singleShot(int(run_seconds * 1000), self.quit)
            else:
                time.sleep(run_seconds)
                self.quit()
                return 0

        if HAS_PYSIDE6 and self.qapp:
            return self.qapp.exec()
        else:
            logger.info("App running (fallback loop). Press Ctrl+C to quit.")
            try:
                while self._running:
                    time.sleep(0.2)
            except KeyboardInterrupt:
                pass
            finally:
                self.quit()
            return 0

    def quit(self) -> None:
        """Cleanly terminate the application and resources."""
        if not self._running:
            return
        logger.info("Quitting netPrep...")
        self._running = False
        self.hotkey.stop()
        self.tray.hide()
        if HAS_PYSIDE6 and self.qapp:
            self.qapp.quit()


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="netPrep Menu-Bar Application")
    parser.add_argument(
        "--test-scan",
        action="store_true",
        help="Trigger a test scan immediately upon startup",
    )
    parser.add_argument(
        "--run-seconds",
        type=float,
        default=None,
        help="Run for N seconds and cleanly exit (useful for automated testing)",
    )
    args = parser.parse_args()

    app = NetPrepApp()
    sys.exit(app.start(run_seconds=args.run_seconds, trigger_scan=args.test_scan))


if __name__ == "__main__":
    main()
