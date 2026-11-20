"""Integration test for OllamaAnswerEngine against local Ollama server.

Automatically skipped if Ollama is not running locally or the model is not pulled.
"""

from __future__ import annotations

import json
import unittest
import urllib.error
import urllib.request

from netprep.answer_engine import OllamaAnswerEngine
from netprep.scan_pipeline import ParsedQuestion
from netprep.subjects import SubjectPack


class TestOllamaLiveIntegration(unittest.TestCase):
    """Integration test connecting to live local Ollama server."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.host = "http://localhost:11434"
        cls.model = "qwen2.5:1.5b"
        tags_url = f"{cls.host}/api/tags"

        # Check if Ollama daemon is reachable
        try:
            req = urllib.request.Request(tags_url, method="GET")
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            raise unittest.SkipTest(f"Ollama server not reachable at {cls.host}: {exc}")

        # Check if model is pulled
        models = [m.get("name") for m in data.get("models", [])]
        model_available = any(
            cls.model in m or m.startswith(cls.model.split(":")[0]) for m in models if m
        )
        if not model_available:
            raise unittest.SkipTest(
                f"Model '{cls.model}' is not pulled in local Ollama. Available: {models}"
            )

    def test_live_answer_inference(self) -> None:
        engine = OllamaAnswerEngine(model_name=self.model, host=self.host)
        question = ParsedQuestion(
            question="Which transport layer protocol provides reliable, connection-oriented data transfer?",
            options={
                "A": "UDP",
                "B": "TCP",
                "C": "IP",
                "D": "ICMP",
            },
        )
        subject = SubjectPack(
            id="computer_networks",
            name="Computer Networks",
            description="Networking protocols",
            prompt_hint="Focus on OSI transport layer reliability.",
            path=Path("subjects/computer_networks"),
            notes_dir=Path("subjects/computer_networks/notes"),
            eval_file=Path("subjects/computer_networks/eval/questions.json"),
        )
        ans = engine.answer(question, subject)
        self.assertIn(ans, {"A", "B", "C", "D"})


if __name__ == "__main__":
    unittest.main()
