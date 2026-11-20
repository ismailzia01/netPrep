# Milestone Report: 04 - Visual Overlay Window (PySide6)

## 1. Summary

This milestone implements the **OverlayRenderer** stage using PySide6 (`netprep/overlay.py`), wiring it into the full scan cycle with robust thread safety, self-capture prevention, configurable timeouts, fallback badges, and error toast banners.

1. **`OverlayWindow` & `PySide6OverlayRenderer` (`netprep/overlay.py`)**:
   - Implements a frameless, transparent, always-on-top, click-through, non-focusing window spanning the capture display.
   - **Click-Through**: Uses `Qt.WindowTransparentForInput` and `setAttribute(Qt.WA_TransparentForMouseEvents, True)` so mouse clicks pass through completely to underlying quiz applications.
   - **Non-Focusing**: Uses `Qt.WindowDoesNotAcceptFocus` and `setAttribute(Qt.WA_ShowWithoutActivating, True)` so keyboard input and active window state remain with the student's browser or quiz window.
   - **Visual Option Marker & Badge**: Highlights the chosen option with a rounded emerald rectangle (`#10B981`) framed by an outer dark outline (`#0F172A`) for high contrast across both light and dark desktop themes. Renders a prominent circular letter badge (`A`–`D`) directly adjacent to the option.
   - **Fallback Top-Center Badge**: When an option bounding box cannot be detected or falls off-screen, renders a centered HUD badge near the top of the screen (`x = (width - 260) / 2`, `y = 40`) indicating the recommended answer letter.
   - **Error Toast Banner**: Displays pipeline error conditions (e.g. *"No question found on screen"*, *"Cannot connect to Ollama server"*, or *"Invalid answer format"*) in a visible top-center slate toast banner with warning icons and actionable messages.
   - **Configurable Auto-Dismissal**: Auto-dismisses after a configurable timeout (default 6.0 seconds), or immediately upon the next scan initiation, or on-demand via the tray menu **Clear marker**.
   - **Design Rule (Non-Negotiable)**: The overlay is a normal, visible window. Under no circumstances will netPrep implement or accept features intended to hide, disguise, or obscure windows from screen capture, screen recording, proctoring tools, or window lists.

2. **Self-Capture Prevention (`netprep/app.py`)**:
   - Before taking a screen capture, the scan pipeline calls `self.overlay.hide()`, flushes pending Qt events with `QApplication.processEvents()`, and waits ~50 ms. This ensures macOS CoreGraphics window server buffers flush cleanly so the subsequent OCR pass never captures ghosted overlay pixels.

3. **Thread Safety Architecture (`netprep/overlay.py`, `netprep/app.py`)**:
   - Heavy background tasks (Quartz screen capture, Apple Vision OCR, question parsing, and local Ollama LLM inference) execute in a background daemon thread, keeping the macOS menu-bar and Qt event loop 100% responsive without UI freezing.
   - All overlay operations (`show_answer`, `show_message`, `hide`) use an internal `_OverlayDispatcher(QObject)` with custom Qt signals (`Signal`) connected with `Qt.QueuedConnection` to ensure all UI manipulation occurs exclusively on the main Qt UI thread.

4. **Tray Status & Menu Controls (`netprep/tray.py`)**:
   - Added **Clear marker** menu action with callback wired to `app.clear_overlay()`.
   - Updated menu tray state to reflect `Ready`, `Scanning...`, `Answer: [B]`, and scan failure messages.

5. **Developer Verification CLI (`scripts/overlay_demo.py`)**:
   - Allows developers to visually inspect answer highlights, bounding boxes, fallback badges, error toasts, and custom durations without initiating a full scan cycle.

---

## 2. Files Created or Changed

| Path | Purpose |
|---|---|
| `netprep/overlay.py` | `OverlayWindow(QWidget)`, `_OverlayDispatcher(QObject)`, and `PySide6OverlayRenderer(OverlayRenderer)`. |
| `netprep/config.py` | Added overlay settings: `overlay_duration`, `overlay_highlight_color`, `overlay_badge_color`, `overlay_text_color`, and `overlay_fallback_position`. |
| `netprep/scan_pipeline.py` | Extended `OverlayRenderer` ABC and `StubOverlayRenderer` with `show_message()` and `clear()`. |
| `netprep/tray.py` | Added "Clear marker" action to `NetPrepTray` and fallback console class; added status updates. |
| `netprep/app.py` | Replaced stub overlay with `PySide6OverlayRenderer`, wired background daemon threading, self-capture flush sequence, and error toast routing. |
| `scripts/overlay_demo.py` | Developer verification CLI for testing overlay geometry, fallback badges, and error banners. |
| `tests/test_overlay.py` | 9 unit tests covering Retina 2x coordinate mapping, badge placement, fallback badge, timeout dismissal, toast banner mode, thread-safe renderer dispatch, clear-before-capture sequence mock, and scan failure error paths. |
| `tests/test_config.py` | Updated unit tests to assert overlay configuration defaults. |
| `README.md` | Documented overlay architecture, window flags, self-capture prevention, configuration, tray controls, developer script, and updated roadmap. |
| `docs/reports/04-overlay.md` | This milestone report. |
| `docs/reports/README.md` | Updated milestone reports index. |

---

## 3. Decisions and Assumptions

1. **Decoupling Qt Signals from ABC (`TypeError: metaclass conflict`)**:
   - Inheriting from both `QObject` (`Shiboken.ObjectType`) and `OverlayRenderer` (`abc.ABCMeta`) produces a fatal Python metaclass conflict.
   - **Decision**: `PySide6OverlayRenderer` implements `OverlayRenderer` cleanly without inheriting from `QObject`. It instantiates an internal `_OverlayDispatcher(QObject)` composition helper that manages Qt signals and slots for thread-safe cross-thread execution.
2. **Window Flags & Transparent Click-Through**:
   - To ensure the overlay never interferes with the student's interaction with the test page, the window uses:
     - `Qt.WindowStaysOnTopHint`: Keeps overlay visible over browser windows.
     - `Qt.FramelessWindowHint`: Removes macOS window frame, title bar, and close buttons.
     - `Qt.WindowTransparentForInput` + `setAttribute(Qt.WA_TransparentForMouseEvents, True)`: Completely ignores mouse clicks, passing them to the window below.
     - `Qt.WindowDoesNotAcceptFocus` + `setAttribute(Qt.WA_ShowWithoutActivating, True)`: Prevents keyboard focus stealing.
3. **Contrast & Dual-Theme Legibility**:
   - Highlighting an option with a single semi-transparent fill can be illegible if the page is pure dark mode or pure white mode.
   - **Decision**: Option bounding boxes are drawn with a 4-pixel emerald fill (`#10B981`, 60% opacity), a solid 2.5-pixel border, and an outer 1-pixel dark slate contrast border (`#0F172A`). This ensures sharp contrast against both light and dark web pages.
4. **Self-Capture Prevention Buffer Sync**:
   - On macOS, calling `window.hide()` does not immediately synchronize the CoreGraphics display buffer. If `screencapture` or `CGWindowListCreateImage` executes on the immediate next microsecond, ghosted overlay pixels could be captured and sent to OCR.
   - **Decision**: In `run_scan_cycle()`, `self.overlay.hide()` is called first, followed by `qapp.processEvents()` and a 50 ms pause (`time.sleep(0.05)`) before invoking `ScreenCapturer.capture()`.
5. **Visible Overlay Rule (Non-Negotiable)**:
   - The application strictly enforces that the overlay is a normal visible window. No anti-capture, proctor-evasion, or hidden-window mechanisms will ever be supported or accepted.

---

## 4. How to Run and Verify

```bash
# 1. Activate Python 3.12 virtual environment
source .venv/bin/activate

# 2. Run unit tests for overlay
pytest -v tests/test_overlay.py

# 3. Run full test suites
pytest -v
python -m unittest discover tests -v

# 4. Developer overlay check script: Normal answer marker with bounding box
python scripts/overlay_demo.py --option B --box 200,320,520,40 --duration 4.0

# 5. Developer overlay check script: Fallback top-center badge (missing bounding box)
python scripts/overlay_demo.py --option A --fallback --duration 4.0

# 6. Developer overlay check script: Error toast banner
python scripts/overlay_demo.py --error "Cannot connect to Ollama server at http://localhost:11434" --duration 5.0

# 7. Check script help documentation
python scripts/overlay_demo.py --help
```

---

## 5. Test Results with Real Command Output

### A. Overlay Unit Test Suite (`pytest -v tests/test_overlay.py`)
```text
$ .venv/bin/pytest -v tests/test_overlay.py
============================= test session starts ==============================
platform darwin -- Python 3.12.16, pytest-9.2.0, pluggy-1.7.0 -- /Users/ismailzia/MyWorkspace/netPrep/.venv/bin/python3.12
cachedir: .pytest_cache
rootdir: /Users/ismailzia/MyWorkspace/netPrep
configfile: pyproject.toml
testpaths: tests
collecting ... collected 9 items

tests/test_overlay.py::TestOverlayCoordinatesAndPlacement::test_fallback_badge_when_box_is_missing PASSED [ 11%]
tests/test_overlay.py::TestOverlayCoordinatesAndPlacement::test_normal_answer_marker_and_badge_placement PASSED [ 22%]
tests/test_overlay.py::TestOverlayCoordinatesAndPlacement::test_retina_coordinate_conversion PASSED [ 33%]
tests/test_overlay.py::TestOverlayCoordinatesAndPlacement::test_timeout_and_dismissal PASSED [ 44%]
tests/test_overlay.py::TestOverlayCoordinatesAndPlacement::test_toast_message_mode PASSED [ 55%]
tests/test_overlay.py::TestPySide6OverlayRendererThreadSafe::test_show_answer_and_hide PASSED [ 66%]
tests/test_overlay.py::TestPySide6OverlayRendererThreadSafe::test_show_message PASSED [ 77%]
tests/test_overlay.py::TestScanCycleSequenceOrder::test_clear_before_capture_order PASSED [ 88%]
tests/test_overlay.py::TestScanCycleSequenceOrder::test_error_message_path_on_scan_failure PASSED [100%]

============================== 9 passed in 0.44s ===============================
```

### B. Full pytest Suite (83 Passed, 2 Skipped)
```text
$ .venv/bin/pytest -v
============================= test session starts ==============================
platform darwin -- Python 3.12.16, pytest-9.2.0, pluggy-1.7.0 -- /Users/ismailzia/MyWorkspace/netPrep/.venv/bin/python3.12
cachedir: .pytest_cache
rootdir: /Users/ismailzia/MyWorkspace/netPrep
configfile: pyproject.toml
testpaths: tests
collecting ... collected 85 items

tests/test_answer_engine.py::TestAnswerLetterExtraction::test_ambiguous_two_letters_replies PASSED [  1%]
tests/test_answer_engine.py::TestAnswerLetterExtraction::test_empty_or_whitespace_reply PASSED [  2%]
tests/test_answer_engine.py::TestAnswerLetterExtraction::test_no_letter_in_reply PASSED [  3%]
tests/test_answer_engine.py::TestAnswerLetterExtraction::test_prefixed_answers PASSED [  4%]
tests/test_answer_engine.py::TestAnswerLetterExtraction::test_single_clean_letters PASSED [  5%]
tests/test_answer_engine.py::TestAnswerLetterExtraction::test_single_letter_with_punctuation PASSED [  7%]
tests/test_answer_engine.py::TestAnswerLetterExtraction::test_structured_json_reply PASSED [  8%]
tests/test_answer_engine.py::TestOllamaAnswerEngine::test_connection_error_includes_exact_fix PASSED [  9%]
tests/test_answer_engine.py::TestOllamaAnswerEngine::test_invalid_answer_returns_invalid_constant PASSED [ 10%]
tests/test_answer_engine.py::TestOllamaAnswerEngine::test_model_missing_error_includes_exact_fix PASSED [ 11%]
tests/test_answer_engine.py::TestOllamaAnswerEngine::test_prompt_formatting_includes_hint_and_options PASSED [ 12%]
tests/test_answer_engine.py::TestOllamaAnswerEngine::test_successful_structured_answer PASSED [ 14%]
tests/test_answer_engine.py::TestOllamaAnswerEngine::test_timeout_error PASSED [ 15%]
tests/test_answer_engine.py::TestOllamaAnswerEngine::test_warmup_connection_failure_returns_false_without_raising PASSED [ 16%]
tests/test_answer_engine.py::TestOllamaAnswerEngine::test_warmup_success PASSED [ 17%]
tests/test_answer_engine.py::TestConfigDefaults::test_app_config_ollama_defaults PASSED [ 18%]
tests/test_answer_integration.py::TestOllamaLiveIntegration::test_live_answer_inference SKIPPED [ 20%]
tests/test_capture.py::TestCoordinateConversion::test_bounding_box_conversions PASSED [ 21%]
tests/test_capture.py::TestCoordinateConversion::test_invalid_scale_factor_raises_value_error PASSED [ 22%]
tests/test_capture.py::TestCoordinateConversion::test_pixel_to_screen_point_retina_scale PASSED [ 23%]
tests/test_capture.py::TestCoordinateConversion::test_pixel_to_screen_point_standard_scale PASSED [ 24%]
tests/test_capture.py::TestCoordinateConversion::test_pixel_to_screen_point_with_origin_offset PASSED [ 25%]
tests/test_capture.py::TestCoordinateConversion::test_screen_to_pixel_point_roundtrip PASSED [ 27%]
tests/test_capture.py::TestCapturedImageDataclass::test_captured_image_dimensions_and_properties PASSED [ 28%]
tests/test_capture.py::TestCapturePermissionsAndConfig::test_config_capture_region_custom_serialization PASSED [ 29%]
tests/test_capture.py::TestCapturePermissionsAndConfig::test_config_capture_region_defaults PASSED [ 30%]
tests/test_capture.py::TestCapturePermissionsAndConfig::test_config_capture_region_malformed_falls_back PASSED [ 31%]
tests/test_capture.py::TestCapturePermissionsAndConfig::test_permission_error_raised_when_untrusted PASSED [ 32%]
tests/test_capture.py::TestMockQuartzCapture::test_quartz_capture_returns_captured_image PASSED [ 34%]
tests/test_config.py::TestConfig::test_config_from_dict_and_to_dict PASSED [ 35%]
tests/test_config.py::TestConfig::test_default_config_values PASSED      [ 36%]
tests/test_config.py::TestConfig::test_load_and_save_config_roundtrip PASSED [ 37%]
tests/test_config.py::TestConfig::test_load_config_malformed_returns_defaults PASSED [ 38%]
tests/test_config.py::TestConfig::test_load_config_missing_file_returns_defaults PASSED [ 40%]
tests/test_eval_format.py::TestEvalFormat::test_real_computer_networks_eval_is_valid PASSED [ 41%]
tests/test_eval_format.py::TestEvalFormat::test_run_evaluation_metrics PASSED [ 42%]
tests/test_eval_format.py::TestEvalFormat::test_validate_detects_duplicate_ids PASSED [ 43%]
tests/test_eval_format.py::TestEvalFormat::test_validate_detects_invalid_answer_letter PASSED [ 44%]
tests/test_eval_format.py::TestEvalFormat::test_validate_detects_invalid_options PASSED [ 45%]
tests/test_eval_format.py::TestEvalFormat::test_validate_detects_non_list_or_empty PASSED [ 47%]
tests/test_eval_metrics.py::TestEvalMetrics::test_check_dataset_balance PASSED [ 48%]
tests/test_eval_metrics.py::TestEvalMetrics::test_compute_latencies_odd_and_even PASSED [ 49%]
tests/test_eval_metrics.py::TestEvalMetrics::test_split_filtering PASSED [ 50%]
tests/test_eval_metrics.py::TestEvalMetrics::test_topic_breakdown_and_letter_distribution PASSED [ 51%]
tests/test_eval_metrics.py::TestValidationAndPersistence::test_comparison_table_generation PASSED [ 52%]
tests/test_eval_metrics.py::TestValidationAndPersistence::test_save_eval_result PASSED [ 54%]
tests/test_eval_metrics.py::TestValidationAndPersistence::test_validation_with_valid_and_missing_split PASSED [ 55%]
tests/test_hotkey.py::TestHotkey::test_hotkey_listener_pause_and_resume PASSED [ 56%]
tests/test_hotkey.py::TestHotkey::test_hotkey_toggle_pause PASSED        [ 57%]
tests/test_hotkey.py::TestHotkey::test_permission_checks_do_not_crash PASSED [ 58%]
tests/test_ocr.py::TestVisionCoordinateConversion::test_bottom_left_vision_to_pixel PASSED [ 60%]
tests/test_ocr.py::TestVisionCoordinateConversion::test_center_box_conversion PASSED [ 61%]
tests/test_ocr.py::TestVisionCoordinateConversion::test_clamping_negative_coordinates PASSED [ 62%]
tests/test_ocr.py::TestVisionCoordinateConversion::test_top_left_vision_to_pixel PASSED [ 63%]
tests/test_ocr.py::TestAppleVisionOcrEngineMocked::test_dict_backward_compatibility PASSED [ 64%]
tests/test_ocr.py::TestAppleVisionOcrEngineMocked::test_extract_mocked_vision_observations PASSED [ 65%]
tests/test_ocr.py::TestAppleVisionOcrEngineMocked::test_non_darwin_raises_runtime_error PASSED [ 67%]
tests/test_ocr.py::TestAppleVisionOcrEngineMocked::test_unsupported_image_type_raises_type_error PASSED [ 68%]
tests/test_ocr_integration.py::TestAppleVisionIntegration::test_synthetic_image_ocr_and_parse SKIPPED [ 69%]
tests/test_overlay.py::TestOverlayCoordinatesAndPlacement::test_fallback_badge_when_box_is_missing PASSED [ 70%]
tests/test_overlay.py::TestOverlayCoordinatesAndPlacement::test_normal_answer_marker_and_badge_placement PASSED [ 71%]
tests/test_overlay.py::TestOverlayCoordinatesAndPlacement::test_retina_coordinate_conversion PASSED [ 72%]
tests/test_overlay.py::TestOverlayCoordinatesAndPlacement::test_timeout_and_dismissal PASSED [ 74%]
tests/test_overlay.py::TestOverlayCoordinatesAndPlacement::test_toast_message_mode PASSED [ 75%]
tests/test_overlay.py::TestPySide6OverlayRendererThreadSafe::test_show_answer_and_hide PASSED [ 76%]
tests/test_overlay.py::TestPySide6OverlayRendererThreadSafe::test_show_message PASSED [ 77%]
tests/test_overlay.py::TestScanCycleSequenceOrder::test_clear_before_capture_order PASSED [ 78%]
tests/test_overlay.py::TestScanCycleSequenceOrder::test_error_message_path_on_scan_failure PASSED [ 80%]
tests/test_parser.py::TestRegexQuestionParser::test_colon_and_lowercase_markers PASSED [ 81%]
tests/test_parser.py::TestRegexQuestionParser::test_duplicate_option_letters_raises_question_not_found PASSED [ 82%]
tests/test_parser.py::TestRegexQuestionParser::test_empty_or_whitespace_input_raises_question_not_found PASSED [ 83%]
tests/test_parser.py::TestRegexQuestionParser::test_five_options_raises_question_not_found PASSED [ 84%]
tests/test_parser.py::TestRegexQuestionParser::test_missing_option_raises_question_not_found PASSED [ 85%]
tests/test_parser.py::TestRegexQuestionParser::test_missing_question_stem_raises_question_not_found PASSED [ 87%]
tests/test_parser.py::TestRegexQuestionParser::test_multiline_question_and_options PASSED [ 88%]
tests/test_parser.py::TestRegexQuestionParser::test_parentheses_markers PASSED [ 89%]
tests/test_parser.py::TestRegexQuestionParser::test_standard_dot_marker PASSED [ 90%]
tests/test_parser.py::TestRegexQuestionParser::test_top_and_bottom_ui_noise_filtering PASSED [ 91%]
tests/test_scan_pipeline.py::TestScanPipeline::test_bounding_box_and_parsed_question PASSED [ 92%]
tests/test_scan_pipeline.py::TestScanPipeline::test_parsed_question_validation_errors PASSED [ 94%]
tests/test_scan_pipeline.py::TestScanPipeline::test_stubs_pipeline_flow PASSED [ 95%]
tests/test_subjects.py::TestSubjects::test_get_subject_pack_by_id_and_name PASSED [ 96%]
tests/test_subjects.py::TestSubjects::test_list_subject_packs PASSED     [ 97%]
tests/test_subjects.py::TestSubjects::test_load_computer_networks_pack PASSED [ 98%]
tests/test_subjects.py::TestSubjects::test_load_custom_pack PASSED       [100%]

======================== 83 passed, 2 skipped in 0.73s =========================
```

### C. Standard Library unittest Output (84 Ran, 2 Skipped)
```text
$ .venv/bin/python -m unittest discover tests -v
Ran 84 tests in 0.464s

OK (skipped=2)
```

### D. Developer Check Script Output (`scripts/overlay_demo.py --help`)
```text
$ .venv/bin/python scripts/overlay_demo.py --help
usage: overlay_demo.py [-h] [--option {A,B,C,D}] [--box BOX] [--fallback]
                       [--error ERROR] [--duration DURATION]

Verify netPrep visual overlay placement, badges, and error banners.

options:
  -h, --help           show this help message and exit
  --option {A,B,C,D}   Answer option letter to highlight (default: B)
  --box BOX            Option bounding box in screen points 'x,y,width,height'
                       (default: 200,320,520,40)
  --fallback           Simulate missing/off-screen box (renders top-center
                       fallback badge)
  --error ERROR        Display sample error message banner instead of answer
                       marker (e.g. 'No question found')
  --duration DURATION  Duration in seconds before overlay automatically
                       dismisses (default: 6.0)
```

---

## 6. PASS / FAIL / NOT VERIFIED

| Item | Status | Proof / Evidence |
|---|---|---|
| `OverlayWindow` Implementation (`netprep/overlay.py`) | **PASS** | Frameless, transparent, click-through (`WA_TransparentForMouseEvents`), non-focusing (`WindowDoesNotAcceptFocus`) window with rounded highlight box and badges. |
| Retina Coordinate Mapping & Placement | **PASS** | `test_retina_coordinate_conversion` and `test_normal_answer_marker_and_badge_placement` verify 2x Retina downscaling and adjacent badge placement. |
| Fallback Top-Center Badge | **PASS** | `test_fallback_badge_when_box_is_missing` verifies that when bounding box is None or empty, fallback badge renders at top-center (`(width - 260) / 2`, `y = 40`). |
| Configurable Auto-Dismissal Timer | **PASS** | `test_timeout_and_dismissal` verifies `QTimer` single-shot timeout initialization and state reset. |
| Visible Error Toast Banner | **PASS** | `test_toast_message_mode` verifies toast banner text formatting, icon, and position. |
| Thread-Safe UI Invocation | **PASS** | `test_show_answer_and_hide` and `test_show_message` verify `PySide6OverlayRenderer` dispatches signals to `_OverlayDispatcher` on the Qt thread. |
| Self-Capture Clear-Before-Capture Order | **PASS** | `test_clear_before_capture_order` verifies `overlay.hide()` and event processing occurs strictly before `capturer.capture()`. |
| Scan Failure Toast Message Path | **PASS** | `test_error_message_path_on_scan_failure` verifies `QuestionNotFoundError` and engine errors trigger `overlay.show_message()`. |
| Tray Menu Integration | **PASS** | Added "Clear marker" action calling `app.clear_overlay()`. |
| Full Test Suite Passing | **PASS** | 83 passed, 2 skipped in pytest; 84 passed in `unittest discover`. |
| Visual Screen Appearance on Physical Display | **NOT VERIFIED** | Running in a headless/sandboxed execution environment without an active physical display session (`-platform offscreen`). Must be verified manually on a live macOS desktop using `python scripts/overlay_demo.py`. |

> [!IMPORTANT]
> **Manual Visual Verification Instructions**:
> Because automated test environments run headless with `-platform offscreen`, visual rendering must be verified on a live macOS desktop:
> 1. Run `python scripts/overlay_demo.py --option B` and verify that an emerald rounded rectangle highlights the option area with a circular `[B]` badge to its left.
> 2. Run `python scripts/overlay_demo.py --fallback --option C` and verify that an emerald badge `Suggested Answer: [C]` appears top-center.
> 3. Run `python scripts/overlay_demo.py --error "No question found on screen"` and verify a dark slate toast banner appears top-center.
> 4. Verify that clicks pass through to whatever window is underneath the overlay.

---

## 7. Known Issues

1. **Headless Screen Dimensions in Offscreen Testing**:
   - In headless testing environments (`QT_QPA_PLATFORM=offscreen`), `primaryScreen().geometry()` returns a default virtual canvas of 800×600 rather than standard Retina screen dimensions (e.g. 1920×1080 or 2560×1600).
   - **Resolution**: Geometry assertions in `tests/test_overlay.py` dynamically query `window.rect().width()` rather than hardcoding full desktop screen resolutions.
2. **CoreGraphics Window Server Buffer Flush Delay**:
   - Calling `window.hide()` in Qt changes widget visibility, but the macOS window server requires ~50 ms before previously rendered frame pixels are guaranteed removed from the screen buffer.
   - **Resolution**: `NetPrepApp.run_scan_cycle()` hides the overlay, flushes the event loop via `qapp.processEvents()`, and waits 50 ms before initiating `ScreenCapturer.capture()`.

---

## 8. Risks for Next Stages (Local Notes RAG Context Retrieval)

1. **Retrieval Latency During Hotkey Scan Cycle**:
   - Injecting a local RAG retrieval step (vector search or BM25 keyword matching over `subjects/<active_subject>/notes/`) between question parsing and LLM inference adds latency. If retrieval takes >500 ms, total cycle time will noticeably increase.
   - **Mitigation**: Pre-index subject notes into memory or a compact SQLite / Chroma / TF-IDF store upon subject selection or startup.
2. **Context Window Limits in 1.5B/2B Models**:
   - Lightweight models (~1.5B parameters) have smaller effective context attention windows and can suffer from "lost in the middle" degradation if large chunks of notes are stuffed into the prompt.
   - **Mitigation**: Retrieve only top-1 or top-2 concise chunks (under 300 words total) focused tightly on the question stem keywords.

---

## 9. Suggested Next Tasks

1. **Local Notes RAG Architecture (`netprep/rag.py`)**:
   - Design and implement a domain-agnostic `NotesRetriever` interface that indexes `.md` / `.txt` files in `subjects/<pack>/notes/`.
2. **Prompt Template Grounding**:
   - Update `netprep/prompts/mcq.txt` to inject retrieved context passages into the LLM prompt while maintaining single-letter output constraints.
3. **Evaluation Benchmark Comparison**:
   - Run `python scripts/run_eval.py` comparing answer accuracy with and without RAG context grounding on complex subject questions.
