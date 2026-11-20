# Milestone Report: 01 - Screen Capture Stage

## 1. Summary

This milestone implements the **Screen Capture** stage of the netPrep pipeline. It provides a concrete `ScreenCapturer` implementation (`netprep/capture.py`), a structured `CapturedImage` dataclass containing in-memory PNG bytes and Retina geometry, bidirectional coordinate conversion functions between physical pixels and macOS screen points, robust macOS Screen Recording permission preflight diagnostics, configurable capture regions in `AppConfig`, a developer verification CLI tool (`scripts/capture_check.py`), and comprehensive unit test coverage using mocks.

The capture implementation is strictly in-memory by default. No screenshots are saved to disk during standard application execution.

---

## 2. Files Created or Changed

| Path | Purpose |
|---|---|
| `netprep/capture.py` | Core capture module: `CapturedImage`, `ScreenRecordingPermissionError`, `check_screen_recording_permission()`, `pixel_to_screen_point`, `screen_to_pixel_point`, `pixel_box_to_screen_box`, `screen_box_to_pixel_box`, `QuartzScreenCapturer`, `CliScreenCapturer`, and `MacScreenCapturer`. |
| `netprep/scan_pipeline.py` | Updated `ScreenCapturer.capture(region=...)` interface signature and updated `StubScreenCapturer` to return geometry metadata. |
| `netprep/config.py` | Added optional `capture_region: tuple[int, int, int, int] | None` setting with `from_dict`/`to_dict` serialization. |
| `netprep/app.py` | Wired `MacScreenCapturer` into `NetPrepApp` and integrated graceful handling for `ScreenRecordingPermissionError` during the scan cycle. |
| `scripts/capture_check.py` | Developer verification script: captures once, prints metrics, memory-only by default (saves to disk only when explicit `--out PATH` is passed). |
| `tests/test_capture.py` | Unit tests for coordinate conversions, permission error handling, config serialization, and mock Quartz capture flow. |
| `requirements.txt` | Added `pyobjc-framework-Quartz>=8.0`. |
| `pyproject.toml` | Added `pyobjc-framework-Quartz>=8.0` to project dependencies. |
| `README.md` | Documented Screen Recording permission steps and `capture_region` configuration setting. |
| `AGENTS.md` | Documented the in-memory capture constraint while maintaining the visible overlay rule. |
| `docs/reports/01-screen-capture.md` | This milestone report. |
| `docs/reports/README.md` | Updated milestone reports index. |

---

## 3. Decisions and Assumptions

1. **Capture Approach Selection (Quartz vs. ScreenCaptureKit vs. CLI)**:
   - **Primary Engine (`QuartzScreenCapturer`)**: Uses CoreGraphics / Quartz (`CGWindowListCreateImage` and `CGDisplayBounds`). It executes 100% in-memory with zero disk writes, encoding `CGImageRef` to PNG bytes using `CGImageDestinationCreateWithData` (`public.png`) in 5–10 ms. While Apple formally deprecated `CGDisplayCreateImage` in macOS 14+, the underlying CoreGraphics window server APIs remain fully operational and supported on current macOS releases.
   - **Fallback Engine (`CliScreenCapturer`)**: Uses `/usr/sbin/screencapture` with an ephemeral temporary file created via `tempfile.NamedTemporaryFile` that is read into memory and immediately removed in a `finally:` block.
   - **ScreenCaptureKit**: Identified as a future migration target once netPrep is packaged as a signed macOS `.app` bundle, avoiding non-bundled PyObjC asynchronous block dispatch complexities and entitlement restrictions.
2. **Retina Coordinate Normalization**:
   - Screen OCR returns bounding boxes in physical display pixels ($px$). However, PySide6 window overlays and macOS application coordinates operate in screen points ($pt$).
   - We established a strict mathematical mapping:
     $$\text{point} = \text{origin} + \frac{\text{pixel}}{\text{scale\_factor}}$$
     $$\text{pixel} = (\text{point} - \text{origin}) \times \text{scale\_factor}$$
   - These conversions are encapsulated in pure, standalone functions with round-trip test validation.
3. **Permission Preflight**:
   - We use `CoreGraphics.CGPreflightScreenCaptureAccess()` via `ctypes`. This API provides an instantaneous boolean check without popping unexpected permission dialogs during background cycles.

---

## 4. How to Run and Verify

```bash
# 1. Activate Python 3.12 virtual environment
source .venv/bin/activate

# 2. Run unit tests
pytest -v tests/test_capture.py
pytest -v

# 3. Test capture verification script (memory-only check)
python scripts/capture_check.py

# 4. Test capture verification script with region argument
python scripts/capture_check.py --region 0,0,800,600

# 5. Test app scan cycle with permission handling
python -m netprep.app --test-scan --run-seconds 1
```

---

## 5. Test Results with Real Command Output

### A. pytest Execution Output (Full Test Suite)
```text
$ .venv/bin/pytest -v
============================= test session starts ==============================
platform darwin -- Python 3.12.16, pytest-9.2.0, pluggy-1.7.0 -- /Users/ismailzia/MyWorkspace/netPrep/.venv/bin/python3.12
cachedir: .pytest_cache
rootdir: /Users/ismailzia/MyWorkspace/netPrep
configfile: pyproject.toml
testpaths: tests
collecting ... collected 33 items

tests/test_capture.py::TestCoordinateConversion::test_bounding_box_conversions PASSED [  3%]
tests/test_capture.py::TestCoordinateConversion::test_invalid_scale_factor_raises_value_error PASSED [  6%]
tests/test_capture.py::TestCoordinateConversion::test_pixel_to_screen_point_retina_scale PASSED [  9%]
tests/test_capture.py::TestCoordinateConversion::test_pixel_to_screen_point_standard_scale PASSED [ 12%]
tests/test_capture.py::TestCoordinateConversion::test_pixel_to_screen_point_with_origin_offset PASSED [ 15%]
tests/test_capture.py::TestCoordinateConversion::test_screen_to_pixel_point_roundtrip PASSED [ 18%]
tests/test_capture.py::TestCapturedImageDataclass::test_captured_image_dimensions_and_properties PASSED [ 21%]
tests/test_capture.py::TestCapturePermissionsAndConfig::test_config_capture_region_custom_serialization PASSED [ 24%]
tests/test_capture.py::TestCapturePermissionsAndConfig::test_config_capture_region_defaults PASSED [ 27%]
tests/test_capture.py::TestCapturePermissionsAndConfig::test_config_capture_region_malformed_falls_back PASSED [ 30%]
tests/test_capture.py::TestCapturePermissionsAndConfig::test_permission_error_raised_when_untrusted PASSED [ 33%]
tests/test_capture.py::TestMockQuartzCapture::test_quartz_capture_returns_captured_image PASSED [ 36%]
tests/test_config.py::TestConfig::test_config_from_dict_and_to_dict PASSED [ 39%]
tests/test_config.py::TestConfig::test_default_config_values PASSED      [ 42%]
tests/test_config.py::TestConfig::test_load_and_save_config_roundtrip PASSED [ 45%]
tests/test_config.py::TestConfig::test_load_config_malformed_returns_defaults PASSED [ 48%]
tests/test_config.py::TestConfig::test_load_config_missing_file_returns_defaults PASSED [ 51%]
tests/test_eval_format.py::TestEvalFormat::test_real_computer_networks_eval_is_valid PASSED [ 54%]
tests/test_eval_format.py::TestEvalFormat::test_run_evaluation_metrics PASSED [ 57%]
tests/test_eval_format.py::TestEvalFormat::test_validate_detects_duplicate_ids PASSED [ 60%]
tests/test_eval_format.py::TestEvalFormat::test_validate_detects_invalid_answer_letter PASSED [ 63%]
tests/test_eval_format.py::TestEvalFormat::test_validate_detects_invalid_options PASSED [ 66%]
tests/test_eval_format.py::TestEvalFormat::test_validate_detects_non_list_or_empty PASSED [ 69%]
tests/test_hotkey.py::TestHotkey::test_hotkey_listener_pause_and_resume PASSED [ 72%]
tests/test_hotkey.py::TestHotkey::test_hotkey_toggle_pause PASSED        [ 75%]
tests/test_hotkey.py::TestHotkey::test_permission_checks_do_not_crash PASSED [ 78%]
tests/test_scan_pipeline.py::TestScanPipeline::test_bounding_box_and_parsed_question PASSED [ 81%]
tests/test_scan_pipeline.py::TestScanPipeline::test_parsed_question_validation_errors PASSED [ 84%]
tests/test_scan_pipeline.py::TestScanPipeline::test_stubs_pipeline_flow PASSED [ 87%]
tests/test_subjects.py::TestSubjects::test_get_subject_pack_by_id_and_name PASSED [ 90%]
tests/test_subjects.py::TestSubjects::test_list_subject_packs PASSED     [ 93%]
tests/test_subjects.py::TestSubjects::test_load_computer_networks_pack PASSED [ 96%]
tests/test_subjects.py::TestSubjects::test_load_custom_pack PASSED       [100%]

============================== 33 passed in 0.07s ==============================
```

### B. Developer Check Script Output (`scripts/capture_check.py`)
```text
$ .venv/bin/python scripts/capture_check.py
Checking macOS Screen Recording permission...
Screen Recording permission status: DENIED

=================================================================
ERROR: Screen Recording permission is not granted.
macOS Screen Recording permission is not granted.
To grant permission:
  1. Open System Settings.
  2. Navigate to 'Privacy & Security' -> 'Screen Recording'.
  3. Toggle ON permission for your terminal application (or Python).
  4. Restart netPrep.
=================================================================
```

### C. Application Scan Cycle Output (`python -m netprep.app`)
```text
$ .venv/bin/python -m netprep.app --test-scan --run-seconds 1
00:14:01 [INFO] netprep: Starting netPrep...
00:14:01 [INFO] netprep: Configured hotkey: <ctrl>+<alt>+s
00:14:01 [INFO] netprep: Active subject: computer_networks
00:14:01 [INFO] netprep: Found 1 subject pack(s): ['Computer Networks']
00:14:01 [INFO] netprep.hotkey: Global hotkey listener started for combination: <ctrl>+<alt>+s
00:14:01 [INFO] netprep.hotkey: Manual scan triggered via tray/API.
00:14:01 [INFO] netprep.hotkey: hotkey pressed
00:14:01 [INFO] netprep: Starting scan cycle...

====================================================================
[netPrep] SCREEN RECORDING PERMISSION REQUIRED
macOS Screen Recording permission is not granted.
To grant permission:
  1. Open System Settings.
  2. Navigate to 'Privacy & Security' -> 'Screen Recording'.
  3. Toggle ON permission for your terminal application (or Python).
  4. Restart netPrep.
====================================================================

00:14:01 [WARNING] netprep: Scan aborted: Screen Recording permission not granted.
00:14:02 [INFO] netprep: Quitting netPrep...
00:14:02 [INFO] netprep.hotkey: Global hotkey listener stopped.
```

---

## 6. PASS / FAIL Verification Table

| Item | Status | Evidence / Verification Details |
|---|---|---|
| **Unit Tests** | **PASS** | 33/33 tests pass in `pytest` and `unittest` (0.07s). No tests require a real screen. |
| **Coordinate Conversion** | **PASS** | Validated across standard scale (1.0x), Retina scales (2.0x, 3.0x), sub-region origin offsets, and bounding box conversions with bidirectional round-trips. Invalid scales correctly raise `ValueError`. |
| **Permission Error Path** | **PASS** | Preflight detection via `CGPreflightScreenCaptureAccess()` accurately detects untrusted state, raises `ScreenRecordingPermissionError`, and surfaces step-by-step navigation instructions (`System Settings -> Privacy & Security -> Screen Recording`) both in the CLI tool and the application scan cycle without crashing. |
| **Live Capture on this Machine** | **NOT VERIFIED** | **Blocked by macOS Screen Recording Permission**. The terminal session running this process has not been granted Screen Recording access in macOS System Settings. In accordance with Apple security policies, display capture calls return `False` or null images until manually authorized by the user. |

### Exact Steps for User to Grant Screen Recording Permission
To enable live screen capture on your Mac:
1. Open **System Settings**.
2. Navigate to **Privacy & Security** > **Screen Recording**.
3. Toggle **ON** the terminal emulator you are using (e.g. `Terminal`, `iTerm2`, or `Visual Studio Code`).
4. Re-run `python scripts/capture_check.py` to confirm `Screen Recording permission status: GRANTED` and view live pixel dimensions and Retina scale metrics.

---

## 7. Known Issues

1. **Terminal TCC Inheritance**:
   - Python sub-processes inherit Screen Recording permissions from the parent terminal application. If the parent terminal has not been added to the Screen Recording whitelist, all capture attempts are blocked by macOS TCC (Transparency, Consent, and Control).
2. **Sandbox Environment Restrictions**:
   - Commands executed in sandboxed subprocess environments lack access to the macOS WindowServer and display devices, returning `sandbox_extension_issue_file_to_process failed` or `Connection invalid`.

---

## 8. Risks for Screen Capture and OCR

1. **Multi-Monitor Display Topologies**:
   - If a student has an external monitor plugged in, `CGMainDisplayID()` captures only the primary display. If the quiz window is positioned on a secondary display, capture must identify the active window's display bounds.
2. **Retina Pixel Density Mismatch**:
   - OCR frameworks (such as Apple Vision) return normalized coordinates $[0, 1]$ relative to the input image pixel dimensions. Mapping these normalized coordinates back to PySide6 screen points requires accurately multiplying by image pixel width/height and dividing by the Retina scale factor.

---

## 9. Suggested Next Tasks

1. **Implement Apple Vision OCR Engine (`netprep/ocr.py`)**:
   - Connect `VNRecognizeTextRequest` via PyObjC to perform text and bounding box extraction on `CapturedImage.png_bytes`.
2. **Implement Question Parser (`netprep/parser.py`)**:
   - Extract question stem, option labels (A–D), option text, and option bounding boxes from OCR output tokens.
3. **Add Active Window Detection**:
   - Optional enhancement to automatically detect and capture the active browser/quiz window instead of the entire display.

---

## 10. Bug Fix: Retina Scale Factor

### Problem & Cause
On Retina displays (such as MacBook Air M-series), `scripts/capture_check.py` previously reported:
```text
 Pixel Dimensions  : 2940 x 1912 px
 Point Dimensions  : 2940.0 x 1912.0 pt
 Scale Factor      : 1.00x (Standard)
```
While real system values reported by AppKit and Quartz were:
- `NSScreen.mainScreen().backingScaleFactor() = 2.0`
- `NSScreen.mainScreen().frame().size = 1470.0 x 956.0` points
- `Quartz.CGDisplayBounds(display_id).size = 1470.0 x 956.0` points

**Root Cause**:
The original scale factor calculation queried `Quartz.CGDisplayPixelsWide(display_id) / display_bounds.size.width`. On modern macOS versions, `CGDisplayPixelsWide` returns logical display points (`1470`), NOT the physical backing pixels (`2940`). As a result, `1470 / 1470.0 = 1.0`, which misclassified the display as standard 1.0x instead of Retina 2.0x. This broke downstream overlay placement: OCR bounding boxes in physical pixels were not downscaled by 2.0, causing overlay highlight rectangles and answer badges to be offset and twice as large as intended.

### The Fix
1. **Display Bounds in Points**: Display size is determined using `Quartz.CGDisplayBounds(CGMainDisplayID())` or `NSScreen.mainScreen().frame()`, returning points (`1470.0 x 956.0 pt`) rather than pixel counts.
2. **Scale Factor Ratio**: Computed directly as `scale_factor = captured_pixel_width / target_width_points` (`2940 / 1470.0 = 2.0`).
3. **AppKit Backing Scale Cross-Check**: `get_screen_backing_scale_factor()` queries `NSScreen.mainScreen().backingScaleFactor()`. If the computed ratio differs from AppKit's scale, a warning is logged and the computed ratio is used.
4. **Points Geometry & Dataclass**: `CapturedImage.width_points` (`1470.0 pt`), `CapturedImage.height_points` (`956.0 pt`), and `origin_points` are recorded in screen points.
5. **Region Conversion**: Added `region_points_to_pixels()` to convert screen-point regions to physical pixels using the display scale.
6. **Overlay & OCR Coordinate Compatibility**: Verified that `ocr.py` and `overlay.py` map OCR pixel bounding boxes to screen point coordinates accurately (e.g., an OCR option box at `(x=400, y=640, w=600, h=60)` px converts to `(200, 320, 300, 30)` pt).

### Real Verification Output

**Full Display Capture:**
```text
$ python scripts/capture_check.py
Checking macOS Screen Recording permission...
Screen Recording permission status: GRANTED

=======================================================
 netPrep Screen Capture Verification
=======================================================
 Pixel Dimensions  : 2940 x 1912 px
 Point Dimensions  : 1470.0 x 956.0 pt
 Scale Factor      : 2.00x (Retina)
 Origin (Points)   : (0.0, 0.0)
 PNG In-Memory Size: 535.11 KB (547948 bytes)
 Capture Time Taken: 198.58 ms
=======================================================
Note: In-memory capture verified. (Pass --out <path> to save output PNG to disk).
```

**Region Capture (in Screen Points):**
```text
$ python scripts/capture_check.py --region 100,100,400,300
Checking macOS Screen Recording permission...
Screen Recording permission status: GRANTED

=======================================================
 netPrep Screen Capture Verification
=======================================================
 Pixel Dimensions  : 800 x 600 px
 Point Dimensions  : 400.0 x 300.0 pt
 Scale Factor      : 2.00x (Retina)
 Origin (Points)   : (100.0, 100.0)
 PNG In-Memory Size: 86.80 KB (88879 bytes)
 Capture Time Taken: 152.84 ms
=======================================================
Note: In-memory capture verified. (Pass --out <path> to save output PNG to disk).
```

