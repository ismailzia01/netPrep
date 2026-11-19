# Contributing to netPrep

Thank you for your interest in contributing to netPrep! We welcome contributions to support more learning domains, improve local LLM reasoning, and refine our macOS tray interface.

## Mandatory Design Guardrail
> **Important**: The answer overlay is a standard, visible desktop window. Under no circumstances will contributions be accepted that attempt to conceal or hide the application window, overlay, or process from screen sharing, proctoring software, or operating system capture tools.

## Development Setup

1. **Prerequisites**:
   - macOS 13+ (Ventura or newer recommended)
   - Python 3.11, 3.12, or 3.13 (Python 3.12 recommended)

2. **Clone and Virtual Environment**:
   ```bash
   git clone https://github.com/your-username/netprep.git
   cd netprep
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Code Style & Formatting**:
   We enforce formatting and linting with `ruff` and `black`:
   ```bash
   ruff check .
   black --check .
   ```

4. **Running Tests**:
   Ensure all unit tests pass before submitting changes:
   ```bash
   pytest
   # or with standard library:
   python3 -m unittest discover tests
   ```

5. **Evaluation Quality Gate**:
   Any PR modifying the inference pipeline or reasoning engines must not decrease overall evaluation accuracy:
   ```bash
   python scripts/run_eval.py --subject computer_networks --engine dummy
   ```

## Pull Request Guidelines

1. Create a feature branch from `main`: `git checkout -b feature/your-feature-name`
2. Keep commits concise, focused, and well-described.
3. Open a pull request using our PR template, detailing what changes were introduced and linking relevant issues.
