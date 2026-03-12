import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.intent_detection import detect_intent


class FakeLLM:
    def __init__(self, content: str) -> None:
        self._content = content

    def invoke(self, prompt: str):
        _ = prompt
        return SimpleNamespace(content=self._content)


class IntentDetectionTests(unittest.TestCase):
    def test_example_messages(self):
        cases = [
            (
                "Schedule meeting tomorrow at 3pm",
                {
                    "intent": "create_event",
                    "title": "meeting",
                    "content": None,
                    "date": "2026-03-12",
                    "time": "15:00",
                },
            ),
            (
                "Add dentist appointment Friday",
                {
                    "intent": "create_event",
                    "title": "dentist appointment",
                    "content": None,
                    "date": "2026-03-13",
                    "time": None,
                },
            ),
            (
                "What do I have this week?",
                {
                    "intent": "query_calendar",
                    "title": None,
                    "content": None,
                    "date": None,
                    "time": None,
                },
            ),
            (
                "Move my meeting to Monday",
                {
                    "intent": "update_event",
                    "title": "meeting",
                    "content": None,
                    "date": "2026-03-16",
                    "time": None,
                },
            ),
            (
                "Cancel lunch with Sam",
                {
                    "intent": "delete_event",
                    "title": "lunch with Sam",
                    "content": None,
                    "date": None,
                    "time": None,
                },
            ),
            (
                "What notes do I have",
                {
                    "intent": "query_notes",
                    "title": None,
                    "content": None,
                    "date": None,
                    "time": None,
                },
            ),
            (
                "Remember to buy groceries",
                {
                    "intent": "create_note",
                    "title": "buy groceries",
                    "content": "buy groceries",
                    "date": None,
                    "time": None,
                },
            ),
            (
                "Edit my grocery note",
                {
                    "intent": "update_note",
                    "title": "grocery",
                    "content": None,
                    "date": None,
                    "time": None,
                },
            ),
            (
                "Delete the grocery note",
                {
                    "intent": "delete_note",
                    "title": "grocery",
                    "content": None,
                    "date": None,
                    "time": None,
                },
            ),
            (
                "Summarize the uploaded paper",
                {
                    "intent": "rag_query",
                    "title": None,
                    "content": None,
                    "date": None,
                    "time": None,
                },
            ),
            (
                "Schedule something",
                {
                    "intent": "needs_clarification",
                    "title": None,
                    "content": None,
                    "date": None,
                    "time": None,
                },
            ),
        ]

        for message, expected in cases:
            with self.subTest(message=message):
                fake_llm = FakeLLM(json.dumps(expected))
                with patch("app.services.intent_detection._get_intent_llm", return_value=fake_llm):
                    result = detect_intent(message)
                self.assertEqual(result["intent"], expected["intent"])
                self.assertEqual(result["title"], expected["title"])
                self.assertEqual(result["content"], expected["content"])
                self.assertEqual(result["date"], expected["date"])
                self.assertEqual(result["time"], expected["time"])
