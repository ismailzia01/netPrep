"""Application entry point for netPrep."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
import time
from pathlib import Path

from netprep.answer_engine import (
    INVALID_ANSWER,
    OllamaAnswerEngine,
    OllamaConnectionError,
    OllamaModelNotFoundError,
    OllamaTimeoutError,
)
from netprep.capture import MacScreenCapturer, ScreenRecordingPermissionError
from netprep.config import AppConfig, load_config
from netprep.hotkey import HotkeyListener
from netprep.ocr import AppleVisionOcrEngine
from netprep.overlay import PySide6OverlayRenderer
from netprep.parser import QuestionNotFoundError, RegexQuestionParser
from netprep.scan_pipeline import (
    AnswerEngine,
    DummyAnswerEngine,
    OcrEngine,
    OverlayRenderer,
    QuestionParser,
    ScreenCapturer,
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

        # Pipeline components
        if sys.platform == "darwin":
            self.capturer: ScreenCapturer = MacScreenCapturer(region=self.config.capture_region)
            self.ocr_engine: OcrEngine = AppleVisionOcrEngine()
        else:
            self.capturer = StubScreenCapturer()
            self.ocr_engine = StubOcrEngine()

        self.parser: QuestionParser = RegexQuestionParser()
        if self.config.model_name.lower() in {"dummy", "stub"}:
            self.answer_engine: AnswerEngine = DummyAnswerEngine()
        else:
            self.answer_engine = OllamaAnswerEngine(
                model_name=self.config.model_name,
                host=self.config.ollama_host,
                timeout=self.config.ollama_timeout,
                keep_alive=self.config.ollama_keep_alive,
            )
        self.overlay: OverlayRenderer = PySide6OverlayRenderer(config=self.config)

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
            on_clear_marker=self.clear_overlay,
            on_quit=self.quit,
        )

        self._signal_timer = None
        if HAS_PYSIDE6 and self.qapp:
            self._signal_timer = QTimer()
            self._signal_timer.timeout.connect(lambda: None)
            self._signal_timer.start(500)

    def _set_status(self, text: str) -> None:
        """Safely update tray status on the Qt UI thread."""
        if HAS_PYSIDE6 and self.qapp:
            QTimer.singleShot(0, lambda: self.tray.update_status(text))
        else:
            self.tray.update_status(text)

    def clear_overlay(self) -> None:
        """Dismiss overlay marker and reset status to Ready."""
        self.overlay.hide()
        self._set_status("Ready")

    def run_scan_cycle(self, synchronous: bool = False) -> None:
        """Initiate scan cycle, hiding existing overlay and offloading work off UI thread."""
        logger.info("Starting scan cycle...")
        self._set_status("Scanning...")

        # 0. Self-capture prevention: clear overlay and flush events before screen grab
        self.overlay.hide()
        if HAS_PYSIDE6 and self.qapp:
            self.qapp.processEvents()

        if synchronous or not HAS_PYSIDE6:
            self._execute_scan()
        else:
            threading.Thread(target=self._execute_scan, daemon=True).start()

    def _execute_scan(self) -> None:
        """Execute capture, OCR, parsing, and reasoning steps."""
        try:
            # Brief frame wait to ensure window server cleared overlay from display memory
            time.sleep(0.05)

            # 1. Screen capture
            image = self.capturer.capture(region=self.config.capture_region)

            # 2. OCR text extraction
            ocr_data = self.ocr_engine.extract(image)

            # 3. Question parsing
            parsed_question = self.parser.parse(ocr_data)

            # 4. Resolve active subject pack
            subject_pack = get_subject_pack(self.config.active_subject, self.config.subjects_dir)

            # 5. Answer prediction
            answer_letter = self.answer_engine.answer(parsed_question, subject=subject_pack)

            if answer_letter == INVALID_ANSWER:
                sys.stderr.write("\n[netPrep] Warning: Model returned an unparseable or ambiguous answer.\n")
                logger.warning("Answer engine returned INVALID response.")
                self.overlay.show_message("Model returned invalid answer")
                self._set_status("Error: Invalid response")
                return

            # 6. Show overlay on screen
            self.overlay.show_answer(answer_letter, parsed_question)
            self._set_status(f"Answer: [{answer_letter}]")
            logger.info("Scan completed successfully. Suggested Answer: [%s]", answer_letter)
        except ScreenRecordingPermissionError as perm_err:
            sys.stderr.write(
                f"\n====================================================================\n"
                f"[netPrep] SCREEN RECORDING PERMISSION REQUIRED\n"
                f"{perm_err}\n"
                f"====================================================================\n\n"
            )
            logger.warning("Scan aborted: Screen Recording permission not granted.")
            self.overlay.show_message("Screen Recording permission required")
            self._set_status("Error: Screen Recording denied")
        except QuestionNotFoundError as q_err:
            sys.stderr.write(f"\n[netPrep] No question found on screen: {q_err}\n")
            logger.warning("Scan aborted: %s", q_err)
            self.overlay.show_message("No question found on screen")
            self._set_status("No question found")
        except OllamaConnectionError as conn_err:
            sys.stderr.write(
                f"\n====================================================================\n"
                f"[netPrep] OLLAMA CONNECTION ERROR\n"
                f"{conn_err}\n"
                f"====================================================================\n\n"
            )
            logger.error("Scan aborted: Ollama server not reachable.")
            self.overlay.show_message("Ollama offline. Run: ollama serve")
            self._set_status("Ollama offline (run: ollama serve)")
        except OllamaModelNotFoundError as model_err:
            sys.stderr.write(
                f"\n====================================================================\n"
                f"[netPrep] OLLAMA MODEL NOT FOUND\n"
                f"{model_err}\n"
                f"====================================================================\n\n"
            )
            logger.error("Scan aborted: %s", model_err)
            self.overlay.show_message(f"Model missing: {self.config.model_name}")
            self._set_status(f"Model missing (run: ollama pull {self.config.model_name})")
        except OllamaTimeoutError as timeout_err:
            sys.stderr.write(f"\n[netPrep] Ollama inference timed out: {timeout_err}\n")
            logger.error("Scan aborted: %s", timeout_err)
            self.overlay.show_message("Ollama inference timed out")
            self._set_status("Model timed out")
        except Exception as exc:
            logger.error("Scan cycle encountered an error: %s", exc, exc_info=True)
            self.overlay.show_message(f"Scan error: {exc}")
            self._set_status(f"Scan error: {exc}")

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

        if isinstance(self.answer_engine, OllamaAnswerEngine):
            self.answer_engine.warmup()

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
