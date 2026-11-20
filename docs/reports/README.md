# netPrep Milestone Reports

This directory contains progress reports, verification proof, test outputs, and risk assessments for each milestone of the netPrep development lifecycle.

## Milestone Index

- [00 - Project Skeleton](00-project-skeleton.md): Initial package structure, pipeline interfaces, PySide6 tray app, global hotkey handling, subject pack architecture, evaluation runner, and contributor guidelines.
- [01 - Screen Capture Stage](01-screen-capture.md): In-memory Quartz screen capture, Retina coordinate normalization functions, macOS Screen Recording permission diagnostics, developer check tool (`scripts/capture_check.py`), and unit test suite.
- [02 - OCR and Question Parsing Stages](02-ocr-parser.md): On-device Apple Vision OCR framework integration, normalized-to-pixel Cartesian coordinate transforms, Regex-based 4-choice question parser, multi-line options and UI noise filtering, developer verification CLI (`scripts/ocr_check.py`), and integration test suite.
- [03 - Local LLM AnswerEngine & Eval Upgrades](03-local-model.md): Ollama local model integration on localhost:11434, single-letter extraction with invalid-answer rejection, model pre-warming, latency percentiles, predicted distributions, and model comparison benchmarking.
- [04 - Visual Overlay Window (PySide6)](04-overlay.md): Frameless transparent click-through non-focusing window, option highlight box and badges, fallback top-center badge, self-capture prevention buffer flush, thread-safe UI dispatch, error toasts, and developer verification script.
