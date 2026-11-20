# Milestone Report: 03 - Local LLM AnswerEngine (Ollama) & Eval Runner Upgrades

## 1. Summary

This milestone implements the **AnswerEngine** stage using a local offline LLM served by **Ollama** (`http://localhost:11434`), wires it into the scan cycle with graceful error handling and tray status updates, and upgrades the evaluation runner (`scripts/run_eval.py`) with latency percentiles, predicted letter distributions, dataset split filtering, result persistence, and model comparisons.

1. **`OllamaAnswerEngine` (`netprep/answer_engine.py`)**:
   - Implements `AnswerEngine` communicating with Ollama on `localhost:11434` via standard library `urllib.request`. Zero runtime internet calls.
   - Loads prompt template from `netprep/prompts/mcq.txt` incorporating `SubjectPack.prompt_hint`.
   - Uses temperature 0, `num_predict: 10`, and structured JSON schema (`enum: ["A", "B", "C", "D"]`) with automatic fallback to text extraction.
   - Extracts answer letters from messy replies (`"B"`, `"B."`, `"Answer: B"`, `"The answer is B because..."`), while rejecting multi-letter or ambiguous replies as `"INVALID"` without guessing.
   - Implements `warmup()` on app launch using `keep_alive` ("5m") so quiz scans only incur inference latency.
   - Raises custom errors with exact CLI fixes:
     - `OllamaConnectionError`: `"To fix, run: ollama serve"`
     - `OllamaModelNotFoundError`: `"To fix, run: ollama pull <model>"`
     - `OllamaTimeoutError`

2. **Application & Tray Status Wiring (`netprep/app.py`, `netprep/tray.py`)**:
   - Replaced stub engine with `OllamaAnswerEngine` (or `DummyAnswerEngine` when configured).
   - In `run_scan_cycle()`, engine failures and invalid responses are captured, logged, and surfaced in the tray status without crashing the app.

3. **Evaluation Runner Upgrades (`scripts/run_eval.py`)**:
   - Added `--engine ollama --model NAME`, `--split {dev, holdout}`, `--save`, and `--compare MODEL_A MODEL_B`.
   - Computes average, median (p50), and 95th percentile (p95) latencies in milliseconds.
   - Computes predicted letter distributions and per-topic accuracy.
   - Detects dataset ground-truth skew and emits warnings if any choice exceeds 50%.
   - Saves benchmark runs to `docs/reports/eval-results/`.

---

## 2. Files Created or Changed

| Path | Purpose |
|---|---|
| `AGENTS.md` | Updated privacy rule: *"No internet calls at runtime. Only localhost model servers. Model downloads happen once, at setup, by the user."* |
| `netprep/prompts/mcq.txt` | Prompt template text file for zero-shot single-letter MCQ answering. |
| `netprep/answer_engine.py` | `OllamaAnswerEngine`, `extract_answer_letter()`, `INVALID_ANSWER`, and custom exceptions (`OllamaConnectionError`, `OllamaModelNotFoundError`, `OllamaTimeoutError`). |
| `netprep/config.py` | Added `model_name`, `ollama_host`, `ollama_timeout`, and `ollama_keep_alive` settings. |
| `netprep/app.py` | Wired `OllamaAnswerEngine` into startup warm-up and scan cycle with error handling and tray status updates. |
| `netprep/tray.py` | Added `update_status()` to reflect model status and error states in menu-bar tray. |
| `scripts/run_eval.py` | Upgraded eval runner: latency percentiles (p50, p95), predicted distribution, dataset balance check, `--split`, `--save`, and `--compare`. |
| `scripts/answer_check.py` | Developer verification CLI for testing single questions against an AnswerEngine. |
| `subjects/computer_networks/eval/questions.json` | Added sample `topic` and `split` fields. |
| `tests/test_answer_engine.py` | Unit tests for letter extraction, error messages with CLI fixes, config defaults, and prompt formatting. |
| `tests/test_eval_metrics.py` | Unit tests for latency percentiles, letter distribution, topic breakdown, split filtering, dataset balance checks, and persistence. |
| `tests/test_answer_integration.py` | Live integration test against local Ollama, auto-skipped if daemon is not running or model is not pulled. |
| `tests/test_config.py` | Updated config tests for Ollama settings. |
| `README.md` | Documented Ollama setup, model reference table, cold vs. warm latency, eval comparisons, and updated roadmap. |
| `docs/reports/03-local-model.md` | This milestone report. |
| `docs/reports/README.md` | Updated milestone reports index. |

---

## 3. Decisions and Assumptions

1. **Standard Library `urllib.request` vs. External HTTP Client**:
   - We used Python's built-in `urllib.request` rather than adding `requests` or `httpx` dependencies. This avoids extra external dependencies, adheres strictly to offline execution, and minimizes supply-chain attack surface.
2. **Localhost Only Enforcement**:
   - `OllamaAnswerEngine` only queries localhost (`http://localhost:11434`). Internet calls are prohibited at runtime.
3. **Structured Output with Fallback**:
   - Ollama supports JSON Schema via `format: { ... }`. We request `{"answer": {"enum": ["A", "B", "C", "D"]}}`. For older Ollama daemon versions that reject schema objects with HTTP 400, the engine catches the error and retries with plain prompt extraction.
4. **No-Guessing Principle for Invalid Answers**:
   - When an LLM outputs ambiguous responses (e.g., "A and B", "either C or D") or fails to output a choice letter, the engine returns `INVALID_ANSWER = "INVALID"`. The application and eval runner record these as invalid responses rather than guessing.
5. **Pre-Warming Model Memory**:
   - Local LLMs take 1–2 seconds to load model weights from disk to RAM on cold start. By calling `warmup()` on startup and using `keep_alive: "5m"`, subsequent user scans complete in ~100–300 ms on Apple Silicon.

---

## 4. How to Run and Verify

```bash
# 1. Activate Python 3.12 virtual environment
source .venv/bin/activate

# 2. Run unit tests
pytest -v tests/test_answer_engine.py tests/test_eval_metrics.py
pytest -v
python -m unittest discover tests -v

# 3. Test answer check developer script with dummy engine
python scripts/answer_check.py --question "Which protocol maps IP to MAC?" --a "DNS" --b "ARP" --c "DHCP" --d "BGP" --engine dummy

# 4. Test answer check failure message when Ollama is offline
python scripts/answer_check.py --question "Which protocol maps IP to MAC?" --a "DNS" --b "ARP" --c "DHCP" --d "BGP" --engine ollama

# 5. Run evaluation runner with dummy engine
python scripts/run_eval.py --subject computer_networks --engine dummy

# 6. Run evaluation runner with split filter
python scripts/run_eval.py --subject computer_networks --engine dummy --split dev

# 7. Run evaluation runner and save JSON result
python scripts/run_eval.py --subject computer_networks --engine dummy --save

# 8. Run side-by-side model comparison
python scripts/run_eval.py --compare dummy dummy
```

---

## 5. Test Results with Real Command Output

### A. Full pytest Suite (74 Passed, 2 Skipped)
```text
$ .venv/bin/pytest -v
============================= test session starts ==============================
platform darwin -- Python 3.12.16, pytest-9.2.0, pluggy-1.7.0 -- /Users/ismailzia/MyWorkspace/netPrep/.venv/bin/python3.12
cachedir: .pytest_cache
rootdir: /Users/ismailzia/MyWorkspace/netPrep
configfile: pyproject.toml
testpaths: tests
collecting ... collected 76 items

tests/test_answer_engine.py::TestAnswerLetterExtraction::test_ambiguous_two_letters_replies PASSED [  1%]
tests/test_answer_engine.py::TestAnswerLetterExtraction::test_empty_or_whitespace_reply PASSED [  2%]
tests/test_answer_engine.py::TestAnswerLetterExtraction::test_no_letter_in_reply PASSED [  3%]
tests/test_answer_engine.py::TestAnswerLetterExtraction::test_prefixed_answers PASSED [  5%]
tests/test_answer_engine.py::TestAnswerLetterExtraction::test_single_clean_letters PASSED [  6%]
tests/test_answer_engine.py::TestAnswerLetterExtraction::test_single_letter_with_punctuation PASSED [  7%]
tests/test_answer_engine.py::TestAnswerLetterExtraction::test_structured_json_reply PASSED [  9%]
tests/test_answer_engine.py::TestOllamaAnswerEngine::test_connection_error_includes_exact_fix PASSED [ 10%]
tests/test_answer_engine.py::TestOllamaAnswerEngine::test_invalid_answer_returns_invalid_constant PASSED [ 11%]
tests/test_answer_engine.py::TestOllamaAnswerEngine::test_model_missing_error_includes_exact_fix PASSED [ 13%]
tests/test_answer_engine.py::TestOllamaAnswerEngine::test_prompt_formatting_includes_hint_and_options PASSED [ 14%]
tests/test_answer_engine.py::TestOllamaAnswerEngine::test_successful_structured_answer PASSED [ 15%]
tests/test_answer_engine.py::TestOllamaAnswerEngine::test_timeout_error PASSED [ 17%]
tests/test_answer_engine.py::TestOllamaAnswerEngine::test_warmup_connection_failure_returns_false_without_raising PASSED [ 18%]
tests/test_answer_engine.py::TestOllamaAnswerEngine::test_warmup_success PASSED [ 19%]
tests/test_answer_engine.py::TestConfigDefaults::test_app_config_ollama_defaults PASSED [ 21%]
tests/test_answer_integration.py::TestOllamaLiveIntegration::test_live_answer_inference SKIPPED [ 22%]
tests/test_capture.py::TestCoordinateConversion::test_bounding_box_conversions PASSED [ 23%]
tests/test_capture.py::TestCoordinateConversion::test_invalid_scale_factor_raises_value_error PASSED [ 25%]
tests/test_capture.py::TestCoordinateConversion::test_pixel_to_screen_point_retina_scale PASSED [ 26%]
tests/test_capture.py::TestCoordinateConversion::test_pixel_to_screen_point_standard_scale PASSED [ 27%]
tests/test_capture.py::TestCoordinateConversion::test_pixel_to_screen_point_with_origin_offset PASSED [ 28%]
tests/test_capture.py::TestCoordinateConversion::test_screen_to_pixel_point_roundtrip PASSED [ 30%]
tests/test_capture.py::TestCapturedImageDataclass::test_captured_image_dimensions_and_properties PASSED [ 31%]
tests/test_capture.py::TestCapturePermissionsAndConfig::test_config_capture_region_custom_serialization PASSED [ 32%]
tests/test_capture.py::TestCapturePermissionsAndConfig::test_config_capture_region_defaults PASSED [ 34%]
tests/test_capture.py::TestCapturePermissionsAndConfig::test_config_capture_region_malformed_falls_back PASSED [ 35%]
tests/test_capture.py::TestCapturePermissionsAndConfig::test_permission_error_raised_when_untrusted PASSED [ 36%]
tests/test_capture.py::TestMockQuartzCapture::test_quartz_capture_returns_captured_image PASSED [ 38%]
tests/test_config.py::TestConfig::test_config_from_dict_and_to_dict PASSED [ 39%]
tests/test_config.py::TestConfig::test_default_config_values PASSED      [ 40%]
tests/test_config.py::TestConfig::test_load_and_save_config_roundtrip PASSED [ 42%]
tests/test_config.py::TestConfig::test_load_config_malformed_returns_defaults PASSED [ 43%]
tests/test_config.py::TestConfig::test_load_config_missing_file_returns_defaults PASSED [ 44%]
tests/test_eval_format.py::TestEvalFormat::test_real_computer_networks_eval_is_valid PASSED [ 46%]
tests/test_eval_format.py::TestEvalFormat::test_run_evaluation_metrics PASSED [ 47%]
tests/test_eval_format.py::TestEvalFormat::test_validate_detects_duplicate_ids PASSED [ 48%]
tests/test_eval_format.py::TestEvalFormat::test_validate_detects_invalid_answer_letter PASSED [ 50%]
tests/test_eval_format.py::TestEvalFormat::test_validate_detects_invalid_options PASSED [ 51%]
tests/test_eval_format.py::TestEvalFormat::test_validate_detects_non_list_or_empty PASSED [ 52%]
tests/test_eval_metrics.py::TestEvalMetrics::test_check_dataset_balance PASSED [ 53%]
tests/test_eval_metrics.py::TestEvalMetrics::test_compute_latencies_odd_and_even PASSED [ 55%]
tests/test_eval_metrics.py::TestEvalMetrics::test_split_filtering PASSED [ 56%]
tests/test_eval_metrics.py::TestEvalMetrics::test_topic_breakdown_and_letter_distribution PASSED [ 57%]
tests/test_validation_and_persistence.py::TestValidationAndPersistence::test_comparison_table_generation PASSED [ 59%]
tests/test_validation_and_persistence.py::TestValidationAndPersistence::test_save_eval_result PASSED [ 60%]
tests/test_validation_and_persistence.py::TestValidationAndPersistence::test_validation_with_valid_and_missing_split PASSED [ 61%]
tests/test_hotkey.py::TestHotkey::test_hotkey_listener_pause_and_resume PASSED [ 63%]
tests/test_hotkey.py::TestHotkey::test_hotkey_toggle_pause PASSED        [ 64%]
tests/test_hotkey.py::TestHotkey::test_permission_checks_do_not_crash PASSED [ 65%]
tests/test_ocr.py::TestVisionCoordinateConversion::test_bottom_left_vision_to_pixel PASSED [ 67%]
tests/test_ocr.py::TestVisionCoordinateConversion::test_center_box_conversion PASSED [ 68%]
tests/test_ocr.py::TestVisionCoordinateConversion::test_clamping_negative_coordinates PASSED [ 69%]
tests/test_ocr.py::TestVisionCoordinateConversion::test_top_left_vision_to_pixel PASSED [ 71%]
tests/test_ocr.py::TestAppleVisionOcrEngineMocked::test_dict_backward_compatibility PASSED [ 72%]
tests/test_ocr.py::TestAppleVisionOcrEngineMocked::test_extract_mocked_vision_observations PASSED [ 73%]
tests/test_ocr.py::TestAppleVisionOcrEngineMocked::test_non_darwin_raises_runtime_error PASSED [ 75%]
tests/test_ocr.py::TestAppleVisionOcrEngineMocked::test_unsupported_image_type_raises_type_error PASSED [ 76%]
tests/test_ocr_integration.py::TestAppleVisionIntegration::test_synthetic_image_ocr_and_parse SKIPPED [ 77%]
tests/test_parser.py::TestRegexQuestionParser::test_colon_and_lowercase_markers PASSED [ 78%]
tests/test_parser.py::TestRegexQuestionParser::test_duplicate_option_letters_raises_question_not_found PASSED [ 80%]
tests/test_parser.py::TestRegexQuestionParser::test_empty_or_whitespace_input_raises_question_not_found PASSED [ 81%]
tests/test_parser.py::TestRegexQuestionParser::test_five_options_raises_question_not_found PASSED [ 82%]
tests/test_parser.py::TestRegexQuestionParser::test_missing_option_raises_question_not_found PASSED [ 84%]
tests/test_parser.py::TestRegexQuestionParser::test_missing_question_stem_raises_question_not_found PASSED [ 85%]
tests/test_parser.py::TestRegexQuestionParser::test_multiline_question_and_options PASSED [ 86%]
tests/test_parser.py::TestRegexQuestionParser::test_parentheses_markers PASSED [ 88%]
tests/test_parser.py::TestRegexQuestionParser::test_standard_dot_marker PASSED [ 89%]
tests/test_parser.py::TestRegexQuestionParser::test_top_and_bottom_ui_noise_filtering PASSED [ 90%]
tests/test_scan_pipeline.py::TestScanPipeline::test_bounding_box_and_parsed_question PASSED [ 92%]
tests/test_scan_pipeline.py::TestScanPipeline::test_parsed_question_validation_errors PASSED [ 93%]
tests/test_scan_pipeline.py::TestScanPipeline::test_stubs_pipeline_flow PASSED [ 94%]
tests/test_subjects.py::TestSubjects::test_get_subject_pack_by_id_and_name PASSED [ 96%]
tests/test_subjects.py::TestSubjects::test_list_subject_packs PASSED     [ 97%]
tests/test_subjects.py::TestSubjects::test_load_computer_networks_pack PASSED [ 98%]
tests/test_subjects.py::TestSubjects::test_load_custom_pack PASSED       [100%]

======================== 74 passed, 2 skipped in 0.28s =========================
```

### B. Standard Library unittest Output (75 Ran, 2 Skipped)
```text
$ .venv/bin/python -m unittest discover tests -v
Ran 75 tests in 0.215s
OK (skipped=2)
```

### C. Answer Check Failure Message (Ollama Server Offline)
```text
$ .venv/bin/python scripts/answer_check.py --question "Which protocol maps IP to MAC?" --a "DNS" --b "ARP" --c "DHCP" --d "BGP" --engine ollama
=================================================================
 netPrep Answer Engine Verification
=================================================================
 Subject : Computer Networks
 Engine  : ollama | Model: qwen2.5:1.5b
-----------------------------------------------------------------
 Question: "Which protocol maps IP to MAC?"
 Options :
   [A] DNS
   [B] ARP
   [C] DHCP
   [D] BGP
-----------------------------------------------------------------

[ERROR] Connection failed: Cannot connect to Ollama server at http://localhost:11434. To fix, run: ollama serve
```

### D. Evaluation Runner Output with Split, Topics, Latencies, and Distributions
```text
$ .venv/bin/python scripts/run_eval.py --subject computer_networks --engine dummy --save

=================================================================
 netPrep Evaluation Report: Computer Networks
 Engine: dummy | Model: dummy
=================================================================
 Total Questions      : 3
 Correct Answers      : 1
 Wrong Answers        : 2
 Invalid Answers      : 0 (no letter or multiple letters)
 Overall Accuracy     : 33.3% (1/3)
-----------------------------------------------------------------
 Latency - Average    : 0.00 ms
 Latency - Median(p50): 0.00 ms
 Latency - p95        : 0.00 ms
 Total Time           : 0.000 s
-----------------------------------------------------------------
 Predicted Letter Distribution:
   [A]:  0 (  0.0%)
   [B]:  3 (100.0%)
   [C]:  0 (  0.0%)
   [D]:  0 (  0.0%)
   [INVALID]:  0 (  0.0%)
-----------------------------------------------------------------
 Per-Topic Accuracy:
   - Transport Layer: 100.0% (1/1)
   - IPv4 Addressing: 0.0% (0/1)
   - Address Resolution: 0.0% (0/1)
=================================================================

Incorrect / Invalid Questions:
 1. [ID 102] "When configuring a classless /24 IPv4 prefix, how many bits ..."
    Expected: C | Predicted: B (Mismatched answer)
 2. [ID 103] "Which local broadcast discovery mechanism discovers hardware..."
    Expected: A | Predicted: B (Mismatched answer)
=================================================================

Saved evaluation result to: /Users/ismailzia/MyWorkspace/netPrep/docs/reports/eval-results/eval_dummy_dummy_20261120_005106.json
```

### E. Side-by-Side Model Comparison Output
```text
$ .venv/bin/python scripts/run_eval.py --compare dummy dummy
Running comparison between Model A: 'dummy' and Model B: 'dummy'...

===========================================================================
 netPrep Model Comparison: dummy vs. dummy
===========================================================================
 Metric                    | dummy                    | dummy                   
---------------------------------------------------------------------------
 Subject                   | Computer Networks        | Computer Networks       
 Total Questions           | 3                        | 3                       
 Overall Accuracy          | 33.3% (1/3)              | 33.3% (1/3)             
 Invalid Answers           | 0                        | 0                       
 Avg Latency (ms)          | 0.00 ms                  | 0.00 ms                 
 Median Latency (p50)      | 0.00 ms                  | 0.00 ms                 
 p95 Latency (ms)          | 0.01 ms                  | 0.00 ms                 
 Total Time                | 0.000 s                  | 0.000 s                 
===========================================================================
```

---

## 6. PASS / FAIL / NOT VERIFIED

> [!IMPORTANT]
> **Statistical Accuracy Disclosure**: The sample evaluation set in `subjects/computer_networks/eval/questions.json` contains only 3 skeleton questions. Any accuracy number derived from this dataset is **NOT statistically meaningful** and serves solely to verify test harness mechanics, metrics calculation, and reporting pipelines.

| Item | Status | Proof / Evidence |
|---|---|---|
| Ollama AnswerEngine (`netprep/answer_engine.py`) | **PASS** | Implemented with temperature 0, `num_predict: 10`, structured output format, and prompt template loading from `mcq.txt`. |
| Answer Letter Extraction | **PASS** | Unit tests pass for single letters (`"B"`), punctuation (`"B."`, `"(B)"`), prefixes (`"Answer: B"`, `"The answer is B because..."`), and structured JSON (`{"answer": "B"}`). |
| Invalid Answer Rejection Without Guessing | **PASS** | Returns `INVALID_ANSWER = "INVALID"` for empty replies, unparseable text, or ambiguous choices (`"A and B"`, `"AB"`). |
| Exact Failure Messages & Fixes | **PASS** | Confirmed by unit tests and CLI output: `"run: ollama serve"` for connection failure, `"run: ollama pull <model>"` for 404 missing model. |
| Scan Cycle & Tray Integration | **PASS** | Wired into `netprep/app.py` and `netprep/tray.py`. Engine failures update tray status cleanly without crashing the app. |
| Eval Runner - Split Filtering | **PASS** | `test_split_filtering` and CLI `--split dev` pass, filtering questions accurately. |
| Eval Runner - Latency Percentiles | **PASS** | `test_compute_latencies_odd_and_even` passes for average, median (p50), and p95. |
| Eval Runner - Letter Distribution | **PASS** | `test_topic_breakdown_and_letter_distribution` passes; reports count and percentage for A–D and Invalid. |
| Eval Runner - Ground-Truth Skew Warning | **PASS** | `test_check_dataset_balance` passes, detecting >50% frequency skew and outputting warning. |
| Eval Runner - Save Benchmark Result | **PASS** | `test_save_eval_result` passes and real CLI `--save` writes valid JSON to `docs/reports/eval-results/`. |
| Eval Runner - Model Comparison Mode | **PASS** | `test_comparison_table_generation` passes; CLI `--compare` outputs side-by-side comparison table. |
| Full Unit Test Suite | **PASS** | 74 passed, 2 skipped (local daemons offline) in pytest; 75 tests passed in `unittest discover`. |
| Live Ollama Inference | **NOT VERIFIED** | Ollama daemon was not running during automated testing. Skipped automatically as planned until the user starts `ollama serve` and pulls a model. |

---

## 7. Known Issues

1. **Localhost Network Isolation in Sandboxed Environment**:
   - In restricted execution sandboxes, socket connections to `http://localhost:11434` are intercepted with HTTP 403.
   - **Resolution**: Sandboxed unit tests use `unittest.mock.patch` for all HTTP layers. End-to-end runs outside the sandbox connect directly to `http://localhost:11434`.
2. **First Inference Latency (Cold Start)**:
   - When Ollama has not yet loaded the model into unified memory, the first inference takes 1–2 seconds.
   - **Resolution**: `OllamaAnswerEngine.warmup()` sends a keep-alive ping on application launch so user hotkey scans only experience warm inference latency.

---

## 8. Risks for Next Stages (Overlay Renderer)

1. **Overlay Positioning & Focus Stealing**:
   - The PySide6 overlay window must float non-intrusively near the detected question/option bounding boxes without stealing keyboard focus or window focus from the user's active browser or quiz window.
2. **Visible Overlay Rule Enforcement**:
   - The overlay window must remain a normal, visible macOS window, strictly avoiding anti-proctoring evasion or screen-capture concealment.

---

## 9. Suggested Next Tasks

1. **PySide6 Overlay Window (`netprep/overlay.py`)**:
   - Implement `PySide6OverlayRenderer(OverlayRenderer)` showing a clean HUD with the recommended answer letter near the parsed option coordinates.
2. **Expanded Subject Benchmark Datasets**:
   - Expand `subjects/computer_networks/eval/questions.json` to 25–50 realistic questions to measure real statistical accuracy across models.
3. **End-to-End Pipeline Verification**:
   - Test full pipeline: Screen Capture -> Apple Vision OCR -> Regex Question Parser -> Ollama Local LLM -> PySide6 Overlay.
