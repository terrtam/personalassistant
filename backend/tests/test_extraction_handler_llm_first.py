import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.assistant.handlers import extraction as extraction_handler
from app.services.conversation_state import PendingIntent, clear_pending


class ExtractionHandlerLLMFirstTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_pending()

    def test_llm_event_details_fill_missing(self):
        pending = PendingIntent(
            intent="extraction",
            title=None,
            date=None,
            time=None,
            content=None,
            bulk_events=[{"title": "meeting", "date": None, "time": None, "duration_minutes": None}],
            event_index=0,
            awaiting_event_details=True,
        )
        with patch(
            "app.services.assistant.handlers.extraction.detect_intent",
            return_value={
                "date": "2026-03-17",
                "time": "17:00",
                "duration_minutes": 60,
            },
        ), patch(
            "app.services.calendar_service.check_event_conflicts",
            return_value=[],
        ):
            response = extraction_handler.handle_pending(
                "tomorrow at 5pm for one hour", pending
            )

        self.assertIsNotNone(response)
        self.assertIn("Confirm Events", response.answer)


if __name__ == "__main__":
    unittest.main()
