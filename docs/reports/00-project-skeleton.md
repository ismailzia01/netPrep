# Milestone Report: 00 - Project Skeleton

## 1. Summary

This milestone establishes the foundational architecture and skeleton for **netPrep**, an open-source macOS menu-bar assistant for practicing multiple-choice questions offline with small local LLMs (~2B). 

The application architecture enforces strict domain decoupling: the screen capture, OCR, question parsing, and overlay rendering components are domain-neutral; only the `AnswerEngine` stage ingests subject packs. The project skeleton includes:
- macOS menu-bar tray implementation using PySide6 (`QSystemTrayIcon`, `QMenu`, `QActionGroup`).
- Global hotkey listener backed by `pynput` with macOS Accessibility / Input Monitoring preflight diagnostics.
- Subject pack loading and dynamic directory scanning (`subjects/`).
- Evaluation runner (`scripts/run_eval.py`) with strict schema validation.
- Initial subject pack for Computer Networks (`subjects/computer_networks/`).
- Contributor documentation, guidelines (`AGENTS.md`, `CONTRIBUTING.md`, `README.md`), and issue/PR templates.
- Explicit, non-negotiable design guardrail: the overlay window is visible and transparent, with zero stealth/anti-proctoring capabilities.

---

## 2. Files Created or Changed

| Path | Purpose |
|---|---|
| `netprep/__init__.py` | Package version and metadata. |
| `netprep/app.py` | Application controller, PySide6 lifecycle, and scan execution coordinator. |
| `netprep/tray.py` | PySide6 system tray icon and popup menu (Scan now, Pause hotkey, Subject submenu, Quit). |
| `netprep/hotkey.py` | Global hotkey listener using `pynput` with macOS permission checking. |
| `netprep/config.py` | `AppConfig` dataclass and YAML/JSON configuration loader. |
| `netprep/subjects.py` | Subject pack discovery and metadata reader (`SubjectPack`). |
| `netprep/scan_pipeline.py` | Abstract pipeline interfaces and stubs (`ScreenCapturer`, `OcrEngine`, `QuestionParser`, `AnswerEngine`, `OverlayRenderer`). |
| `subjects/computer_networks/pack.yaml` | Computer Networks subject pack metadata. |
| `subjects/computer_networks/notes/.gitkeep` | Placeholder for offline reference notes. |
| `subjects/computer_networks/eval/questions.json` | 3 evaluation MCQs following schema requirements. |
| `scripts/run_eval.py` | Evaluation runner with schema validation, accuracy metrics, and latency measurement. |
| `tests/__init__.py` | Test package definition. |
| `tests/test_config.py` | Unit tests for configuration loading, saving, and defaults. |
| `tests/test_subjects.py` | Unit tests for subject discovery and metadata extraction. |
| `tests/test_eval_format.py` | Unit tests for dataset format validation and evaluation metrics. |
| `tests/test_scan_pipeline.py` | Unit tests for pipeline dataclasses and stub flow. |
| `tests/test_hotkey.py` | Unit tests for hotkey listener pause/resume states. |
| `pyproject.toml` | Project configuration and build specifications. |
| `requirements.txt` | Core package dependencies (`PySide6-Essentials`, `pynput`, `PyYAML`, `pytest`). |
| `.gitignore` | Ignore rules for Python, macOS `.DS_Store`, venvs, and `.env`. |
| `LICENSE` | MIT License. |
| `README.md` | Architecture, pipeline diagram, setup, usage, roadmap, and visible overlay rule. |
| `CONTRIBUTING.md` | Development guidelines, code standards, PR flow, and guardrails. |
| `AGENTS.md` | Development rules for human and AI contributors. |
| `.github/ISSUE_TEMPLATE/` | Bug report and feature request issue templates. |
| `.github/pull_request_template.md` | Pull request template with quality checklists. |
| `docs/reports/00-project-skeleton.md` | This milestone report. |
| `docs/reports/README.md` | Milestone reports index. |

---

## 3. Decisions and Assumptions

1. **Python Version Selection**:
   - The host system had Homebrew Python 3.14.6 and Python 3.15.0_1 installed.
   - However, `PySide6` does not yet offer prebuilt universal2 wheels for Python 3.14 or 3.15. Attempting to install wheels failed distribution resolution.
   - We installed `python@3.12` (Python 3.12.16) via Homebrew and created `.venv` with Python 3.12, which has official universal2 wheels for PySide6 and full `pynput`/`pyobjc` support.
2. **PySide6-Essentials vs. Full PySide6**:
   - We selected `PySide6-Essentials>=6.6.0` instead of the full `PySide6` umbrella package.
   - `PySide6-Essentials` includes `PySide6.QtCore`, `PySide6.QtGui`, and `PySide6.QtWidgets` (which power `QSystemTrayIcon`, `QMenu`, `QAction`, and window management). It eliminates over 350 MB of unneeded dependencies such as `PySide6_WebEngine` (Chromium browser engine) and `PySide6_Addons`.
3. **Subject-Agnostic Boundary**:
   - Only `AnswerEngine.answer()` accepts an optional `SubjectPack`. All upstream stages (`ScreenCapturer`, `OcrEngine`, `QuestionParser`) and downstream stages (`OverlayRenderer`) strictly do not import or access subject data.
4. **macOS Permission Handling**:
   - Listening to keystrokes outside the terminal window requires macOS Accessibility (`AXIsProcessTrusted`) and Input Monitoring (`CGPreflightListenEventAccess`).
   - Rather than crashing or aborting when permissions are missing, the application issues clear warning instructions and continues running so users can still trigger scans via the tray menu.

---

## 4. How to Run and Verify

```bash
# 1. Activate Python 3.12 virtual environment
source .venv/bin/activate

# 2. Run unit test suite with pytest
pytest -v

# 3. Run unit test suite with standard library unittest
python3 -m unittest discover tests -v

# 4. Run the evaluation benchmark
python scripts/run_eval.py --subject computer_networks --engine dummy

# 5. Launch the tray application
python -m netprep.app
```

---

## 5. Test Results with Real Command Output

### A. pytest Execution Output
```text
$ .venv/bin/pytest -v
============================= test session starts ==============================
platform darwin -- Python 3.12.16, pytest-9.2.0, pluggy-1.7.0 -- /Users/ismailzia/MyWorkspace/netPrep/.venv/bin/python3.12
cachedir: .pytest_cache
rootdir: /Users/ismailzia/MyWorkspace/netPrep
configfile: pyproject.toml
testpaths: tests
collecting ... collected 21 items

tests/test_config.py::TestConfig::test_config_from_dict_and_to_dict PASSED [  4%]
tests/test_config.py::TestConfig::test_default_config_values PASSED      [  9%]
tests/test_config.py::TestConfig::test_load_and_save_config_roundtrip PASSED [ 14%]
tests/test_config.py::TestConfig::test_load_config_malformed_returns_defaults PASSED [ 19%]
tests/test_config.py::TestConfig::test_load_config_missing_file_returns_defaults PASSED [ 23%]
tests/test_eval_format.py::TestEvalFormat::test_real_computer_networks_eval_is_valid PASSED [ 28%]
tests/test_eval_format.py::TestEvalFormat::test_run_evaluation_metrics PASSED [ 33%]
tests/test_eval_format.py::TestEvalFormat::test_validate_detects_duplicate_ids PASSED [ 38%]
tests/test_eval_format.py::TestEvalFormat::test_validate_detects_invalid_answer_letter PASSED [ 42%]
tests/test_eval_format.py::TestEvalFormat::test_validate_detects_invalid_options PASSED [ 47%]
tests/test_eval_format.py::TestEvalFormat::test_validate_detects_non_list_or_empty PASSED [ 52%]
tests/test_hotkey.py::TestHotkey::test_hotkey_listener_pause_and_resume PASSED [ 57%]
tests/test_hotkey.py::TestHotkey::test_hotkey_toggle_pause PASSED        [ 61%]
tests/test_hotkey.py::TestHotkey::test_permission_checks_do_not_crash PASSED [ 66%]
tests/test_scan_pipeline.py::TestScanPipeline::test_bounding_box_and_parsed_question PASSED [ 71%]
tests/test_scan_pipeline.py::TestScanPipeline::test_parsed_question_validation_errors PASSED [ 76%]
tests/test_scan_pipeline.py::TestScanPipeline::test_stubs_pipeline_flow PASSED [ 80%]
tests/test_subjects.py::TestSubjects::test_get_subject_pack_by_id_and_name PASSED [ 85%]
tests/test_subjects.py::TestSubjects::test_list_subject_packs PASSED     [ 90%]
tests/test_subjects.py::TestSubjects::test_load_computer_networks_pack PASSED [ 95%]
tests/test_subjects.py::TestSubjects::test_load_custom_pack PASSED       [100%]

============================== 21 passed in 0.03s ==============================
```

### B. Evaluation Runner Output
```text
$ .venv/bin/python scripts/run_eval.py --subject computer_networks --engine dummy

=================================================================
 netPrep Evaluation Report: Computer Networks
 Engine: dummy
=================================================================
 Total Questions      : 3
 Correct Answers      : 1
 Wrong Answers        : 2
 Invalid Answers      : 0 (no letter or multiple letters)
 Overall Accuracy     : 33.3% (1/3)
 Average Time/Question: 0.00 ms
 Total Evaluation Time: 0.000 s
=================================================================

Incorrect / Invalid Questions:
 1. [ID 102] "When configuring a classless /24 IPv4 prefix, how many bits ..."
    Expected: C | Predicted: B (Mismatched answer)
 2. [ID 103] "Which local broadcast discovery mechanism discovers hardware..."
    Expected: A | Predicted: B (Mismatched answer)
=================================================================
```

### C. App Execution Output (PySide6 Runtime)
```text
$ .venv/bin/python -m netprep.app --run-seconds 3
23:54:23 [INFO] netprep: Starting netPrep...
23:54:23 [INFO] netprep: Configured hotkey: <ctrl>+<alt>+s
23:54:23 [INFO] netprep: Active subject: computer_networks
23:54:23 [INFO] netprep: Found 1 subject pack(s): ['Computer Networks']

====================================================================
[netPrep] NOTICE: macOS Accessibility or Input Monitoring
permissions are not yet granted for this terminal/app.
Global hotkeys may not detect keystrokes outside this window.
To enable: Open System Settings -> Privacy & Security ->
Accessibility (and Input Monitoring), then enable your terminal/Python.
The app will continue running; you can also click 'Scan now' in the tray.
====================================================================

23:54:23 [WARNING] netprep.hotkey: Missing macOS Accessibility (ax=False) or Input Monitoring (input=False) permission.
23:54:23 [INFO] netprep.hotkey: Global hotkey listener started for combination: <ctrl>+<alt>+s
23:54:23 [WARNING] pynput.keyboard.GlobalHotKeys: This process is not trusted! Input event monitoring will not be possible until it is added to accessibility clients.
23:54:26 [INFO] netprep: Quitting netPrep...
23:54:26 [INFO] netprep.hotkey: Global hotkey listener stopped.
```

---

## 6. PASS / FAIL Verification Table

| Item | Status | Evidence / Verification Details |
|---|---|---|
| **Python Environment & Dependencies** | **PASS** | Python 3.12.16 installed via Homebrew. All dependencies (`PySide6-Essentials`, `pynput`, `pyyaml`, `pytest`, `pyobjc`) installed in `.venv` and verified importable. |
| **Eval Runner** | **PASS** | `python scripts/run_eval.py --subject computer_networks --engine dummy` runs, validates schema, calculates accuracy (33.3%), measures latency, and outputs incorrect questions. |
| **Unit Tests** | **PASS** | 21/21 tests pass via `pytest` and `unittest` in 0.03s. |
| **Clean Quit** | **PASS** | `app.quit()` cleanly shuts down the hotkey listener thread, hides the tray icon, and terminates the event loop with return code 0. |
| **Real Tray Icon (Menu Bar Display)** | **NOT VERIFIED** | `PySide6.QtWidgets.QSystemTrayIcon` is initialized, assigned a programmatic icon, and `.show()` is called. However, verifying that the physical icon appeared in the macOS menu bar via `screencapture -x` failed with `could not create image from display` because Screen Recording permission is not granted to the execution process. |
| **Subject Submenu (Interactive Click)** | **NOT VERIFIED** | Submenu data structures and dynamic population from `subjects/` are verified programmatically (`QActionGroup` exclusivity and checkmarks). However, physical click interaction by a user from the macOS status bar cannot be automated without accessibility permissions. |
| **Real Global Hotkey Keypress** | **NOT VERIFIED** | **Blocked by macOS Permissions**. `pynput` outputs: `[WARNING] pynput.keyboard.GlobalHotKeys: This process is not trusted! Input event monitoring will not be possible until it is added to accessibility clients.` Attempting to send a synthetic keypress via `osascript` fails with `System Events got an error: osascript is not allowed to send keystrokes. (1002)`. |

### Actions Required by the User for Hotkey & Display Verification
To enable real global hotkey detection on your Mac:
1. Open **System Settings** > **Privacy & Security** > **Accessibility**.
2. Add and toggle **ON** the terminal emulator you are using (e.g. `Terminal.app`, `iTerm.app`, or `Visual Studio Code`).
3. Open **System Settings** > **Privacy & Security** > **Input Monitoring**.
4. Verify your terminal is toggled **ON**.
5. Once enabled, restart `python -m netprep.app` and press `<Ctrl>+<Alt>+S` from any application.

---

## 7. Known Issues

1. **macOS Event Tap Restrictions**:
   - `pynput` relies on macOS CoreGraphics event taps (`CGEventTapCreate`). On macOS 13+, global taps fail silently or log a warning if accessibility is untrusted.
2. **Sandbox Restrictions in CI / Agent Environments**:
   - Sandboxed or headless processes lack WindowServer and display access, meaning tray rendering and screen capture require running with unsandboxed / user-level display sessions.

---

## 8. Risks for Screen Capture and OCR

1. **Screen Recording Permissions**:
   - In macOS Sonoma and Sequoia, screen capture via CoreGraphics (`CGDisplayCreateImage`, `CGWindowListCreateImage`) requires explicit **Screen Recording** permission. Unpermissioned capture returns empty/black frames without raising a Python exception.
2. **Retina Display Coordinate Scaling**:
   - Option bounding boxes on Retina displays (2x or 3x scale factor) differ between pixel coordinates (used by OCR engines) and point coordinates (used by Qt / AppKit overlay windows). A normalization layer will be required.
3. **Apple Vision OCR Latency**:
   - Apple Vision framework (`VNRecognizeTextRequest`) running on Neural Engine is fast (~50-100ms) but requires bridging through PyObjC (`Vision` framework). Fallback engines or thread offloading will be required to keep the UI tray responsive.

---

## 9. Suggested Next Tasks

1. **Implement `ScreenCapturer`**:
   - Use `Quartz.CGWindowListCreateImage` or `ScreenCaptureKit` via PyObjC to capture display areas, with permission preflight detection.
2. **Implement `OcrEngine` with Apple Vision**:
   - Bridge `Vision.VNRecognizeTextRequest` to extract word bounding boxes and text blocks.
3. **Implement `QuestionParser`**:
   - Develop spatial heuristic parser that groups text into question stems and options (A–D) using bounding box geometry.
4. **Transparent Overlay Window**:
   - Build a `FramelessWindowHint` PySide6 overlay window that places subtle indicator badges next to detected option bounding boxes.
