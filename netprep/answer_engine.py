"""Ollama AnswerEngine communicating with local Ollama server for MCQ reasoning."""

from __future__ import annotations

import json
import logging
import re
import socket
import urllib.error
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Any

from netprep.scan_pipeline import AnswerEngine, ParsedQuestion

if TYPE_CHECKING:
    from netprep.subjects import SubjectPack

logger = logging.getLogger(__name__)

# Constant indicator for invalid answer format
INVALID_ANSWER = "INVALID"

DEFAULT_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "mcq.txt"

# Default fallback prompt template if file is missing
FALLBACK_PROMPT_TEMPLATE = """You are an expert tutor.
{prompt_hint}

Answer the following multiple-choice question.
Output ONLY the single letter corresponding to the correct answer (A, B, C, or D).
Do not provide any explanation, preamble, or additional text.

Question:
{question}

Options:
{options}

Answer:"""


class OllamaConnectionError(RuntimeError):
    """Raised when netPrep cannot reach the local Ollama server."""


class OllamaModelNotFoundError(RuntimeError):
    """Raised when the requested model is not pulled in Ollama."""


class OllamaTimeoutError(RuntimeError):
    """Raised when an Ollama inference request exceeds the configured timeout."""


def extract_answer_letter(reply_text: str) -> str:
    """Extract a single answer letter (A-D) from raw LLM reply text.

    Returns the uppercase letter ('A', 'B', 'C', 'D') or INVALID_ANSWER ('INVALID').
    Never guesses.
    """
    if not reply_text:
        return INVALID_ANSWER

    cleaned = reply_text.strip()
    if not cleaned:
        return INVALID_ANSWER

    # 1. Structured JSON output: e.g. {"answer": "B"}
    if cleaned.startswith("{") and cleaned.endswith("}"):
        try:
            data = json.loads(cleaned)
            if isinstance(data, dict):
                ans = str(data.get("answer", "")).strip().upper()
                if ans in {"A", "B", "C", "D"}:
                    return ans
        except json.JSONDecodeError:
            pass

    # 2. Standalone letter, possibly with punctuation: "B", "B.", "(B)", "B:"
    single_match = re.fullmatch(r"^\s*\(?([A-Da-d])\)?[.:]?\s*$", cleaned)
    if single_match:
        return single_match.group(1).upper()

    # 3. Explicit prefix patterns: "Answer: B", "The answer is B", "Option: B", "Correct answer: B"
    prefix_match = re.search(
        r"(?:answer|choice|option|correct\s+answer)(?:\s+is)?[:\s]+(?:\()?([A-Da-d])(?:\))?(?:\b|[.:\s]|$)",
        cleaned,
        re.IGNORECASE,
    )
    if prefix_match:
        return prefix_match.group(1).upper()

    # 4. Text starting with the letter: "B because...", "B. Explanation..."
    start_match = re.match(r"^\s*([A-Da-d])(?:\b|[.:\s])", cleaned)
    if start_match:
        rest = cleaned[start_match.end() :]
        if re.search(r"\b(?:and|or|vs)\s+([A-Da-d])\b", rest, re.IGNORECASE):
            return INVALID_ANSWER
        return start_match.group(1).upper()

    # 5. Search for standalone letters A-D across text
    found_letters = re.findall(r"\b([A-Da-d])\b", cleaned)
    unique_letters = list(
        dict.fromkeys(
            letter.upper() for letter in found_letters if letter.upper() in {"A", "B", "C", "D"}
        )
    )
    if len(unique_letters) == 1:
        return unique_letters[0]

    return INVALID_ANSWER


class OllamaAnswerEngine(AnswerEngine):
    """Answers multiple-choice questions via a local Ollama instance on localhost:11434."""

    def __init__(
        self,
        model_name: str = "qwen2.5:1.5b",
        host: str = "http://localhost:11434",
        timeout: float = 15.0,
        keep_alive: str = "5m",
        prompt_template_path: Path | str | None = None,
    ) -> None:
        self.model_name = model_name
        self.host = host.rstrip("/")
        self.timeout = timeout
        self.keep_alive = keep_alive
        self.prompt_template_path = (
            Path(prompt_template_path) if prompt_template_path else DEFAULT_PROMPT_PATH
        )
        self._template = self._load_prompt_template()

    def _load_prompt_template(self) -> str:
        """Load prompt template from text file, falling back to built-in template."""
        if self.prompt_template_path.exists():
            try:
                return self.prompt_template_path.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning("Failed to read prompt template at %s: %s", self.prompt_template_path, exc)
        return FALLBACK_PROMPT_TEMPLATE

    def _format_prompt(self, question: ParsedQuestion, subject: SubjectPack | None) -> str:
        """Render prompt template with subject hint and question options."""
        hint = subject.prompt_hint if subject and subject.prompt_hint else ""
        formatted_options = "\n".join(
            f"{letter}. {text}" for letter, text in sorted(question.options.items())
        )
        return self._template.format(
            prompt_hint=hint,
            question=question.question.strip(),
            options=formatted_options,
        )

    def _build_payload(self, prompt: str, use_schema: bool = True) -> dict[str, Any]:
        """Construct the Ollama /api/generate request payload."""
        payload: dict[str, Any] = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.0,
                "num_predict": 10,
            },
            "keep_alive": self.keep_alive,
        }
        if use_schema:
            payload["format"] = {
                "type": "object",
                "properties": {
                    "answer": {
                        "type": "string",
                        "enum": ["A", "B", "C", "D"],
                    }
                },
                "required": ["answer"],
            }
        return payload

    def _send_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Send HTTP POST request to Ollama with comprehensive error handling."""
        endpoint = f"{self.host}/api/generate"
        req_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=req_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw_bytes = resp.read()
                return json.loads(raw_bytes.decode("utf-8"))
        except urllib.error.HTTPError as http_err:
            if http_err.code == 404:
                raise OllamaModelNotFoundError(
                    f"Model '{self.model_name}' is not available in Ollama. "
                    f"To fix, run: ollama pull {self.model_name}"
                ) from http_err
            err_body = http_err.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Ollama HTTP error {http_err.code}: {err_body}") from http_err
        except urllib.error.URLError as url_err:
            raise OllamaConnectionError(
                f"Cannot connect to Ollama server at {self.host}. "
                "To fix, run: ollama serve"
            ) from url_err
        except (TimeoutError, socket.timeout) as timeout_err:
            raise OllamaTimeoutError(
                f"Ollama request timed out after {self.timeout}s."
            ) from timeout_err

    def warmup(self) -> bool:
        """Preload model weights into memory using keep_alive.

        Returns True on success, False if Ollama server is unreachable or model missing.
        """
        logger.info("Warming up Ollama model '%s' (keep_alive=%s)...", self.model_name, self.keep_alive)
        payload = {
            "model": self.model_name,
            "prompt": "",
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": {"num_predict": 1},
        }
        try:
            self._send_request(payload)
            logger.info("Ollama model '%s' warmed up successfully.", self.model_name)
            return True
        except (OllamaConnectionError, OllamaModelNotFoundError, OllamaTimeoutError) as exc:
            logger.warning("Ollama warm-up skipped: %s", exc)
            return False
        except Exception as exc:
            logger.warning("Ollama warm-up encountered unexpected error: %s", exc)
            return False

    def answer(self, question: ParsedQuestion, subject: SubjectPack | None = None) -> str:
        """Predict the answer letter (A-D) using Ollama.

        Returns 'A', 'B', 'C', 'D' or 'INVALID'. Never guesses.
        """
        prompt = self._format_prompt(question, subject)
        logger.debug("Prompt rendered for Ollama:\n%s", prompt)

        try:
            # Try structured JSON schema first
            payload = self._build_payload(prompt, use_schema=True)
            res = self._send_request(payload)
        except (OllamaConnectionError, OllamaModelNotFoundError, OllamaTimeoutError):
            # Do not retry on connection or model missing errors
            raise
        except Exception as exc:
            # If schema rejected by older Ollama, fallback to plain prompt
            logger.debug("Structured schema request failed (%s). Retrying without schema.", exc)
            payload = self._build_payload(prompt, use_schema=False)
            res = self._send_request(payload)

        raw_response = str(res.get("response", ""))
        logger.debug("Raw Ollama response: '%s'", raw_response)

        extracted = extract_answer_letter(raw_response)
        if extracted == INVALID_ANSWER:
            logger.warning(
                "Ollama produced unparseable answer for question: '%s...'. Response: '%s'",
                question.question[:40],
                raw_response,
            )
        return extracted
