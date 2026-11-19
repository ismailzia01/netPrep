# AGENTS.md - netPrep Development Guidelines

Guidelines and rules for human contributors and AI assistants working on netPrep.

## 1. Core Principles & Philosophy
- **Subject-Agnostic Core**: Pipeline stages (`ScreenCapturer`, `OcrEngine`, `QuestionParser`, `OverlayRenderer`) must remain completely domain-agnostic. Only `AnswerEngine` may access or ingest subject packs.
- **Privacy & Completely Offline**: The application operates 100% offline at runtime. No external network requests, analytics, or telemetry calls are allowed during application execution.
- **Visible Overlay Rule (Non-Negotiable)**: The answer overlay is a normal, visible window. Never implement features that hide the overlay or application windows from screen capture, screen recording, proctoring tools, or window lists.

## 2. Technical Stack & Code Standards
- **Python Version**: Python 3.11+ required. Utilize modern Python typing features (`from __future__ import annotations`, `|` union operators, `dataclass(frozen=...)`).
- **Strict Typing**: All functions, methods, and parameters must have explicit type annotations.
- **Function Size**: Keep functions focused and concise (ideally under 35-40 lines). Extract single-purpose helpers.
- **Error Handling**: Never swallow exceptions silently. Log informative errors with contextual details and provide graceful fallbacks (e.g. for macOS accessibility permissions).
- **Secrets & Credentials**: Never check API keys, tokens, or credentials into the repository.

## 3. Testing & Verification Requirements
- Every new feature, parser, or engine must be accompanied by unit tests in `tests/`.
- Test suites must be runnable via `pytest` as well as Python standard library `unittest` (`python -m unittest discover tests`).
- The evaluation suite (`scripts/run_eval.py`) must pass validation without errors. Any pull request must maintain or improve evaluation accuracy.
