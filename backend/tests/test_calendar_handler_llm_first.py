import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.assistant.handlers import calendar as calendar_handler
from app.services.conversation_state import clear_pending


class CalendarHandlerLLMFirstTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_pending()

    def test_llm_duration_used_for_create(self):
        intent_data = {
            "title": "meeting",
            "date": "2026-03-17",
            "time": "17:00",
            "duration_minutes": 60,
        }
        with patch("app.services.calendar_service.create_event", return_value="ok") as mocked:
            response = calendar_handler.handle_intent(
                "meeting tomorrow at 5pm for one hour", "create_event", intent_data
            )

        self.assertIsNotNone(response)
        self.assertEqual(response.answer, "ok")
        mocked.assert_called_once_with("meeting", "2026-03-17", "17:00", 60)

    def test_duration_falls_back_to_parser(self):
        intent_data = {
            "title": "meeting",
            "date": "2026-03-17",
            "time": "17:00",
            "duration_minutes": None,
        }
        with patch("app.services.calendar_service.create_event", return_value="ok") as mocked:
            response = calendar_handler.handle_intent(
                "meeting tomorrow at 5pm for 45 minutes", "create_event", intent_data
            )

        self.assertIsNotNone(response)
        self.assertEqual(response.answer, "ok")
        mocked.assert_called_once_with("meeting", "2026-03-17", "17:00", 45)

    def test_ambiguous_time_prompts_clarification(self):
        intent_data = {
            "title": "meeting",
            "date": "2026-03-17",
            "time": None,
            "duration_minutes": 60,
        }
        response = calendar_handler.handle_intent(
            "meeting tomorrow at 5", "create_event", intent_data
        )
        self.assertIsNotNone(response)
        self.assertIn("Clarification Needed", response.answer)


if __name__ == "__main__":
    unittest.main()
