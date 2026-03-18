import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.assistant.handlers import notes as notes_handler
from app.services.conversation_state import PendingIntent, clear_pending


class NotesHandlerLLMFirstTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_pending()

    def test_llm_content_used_for_pending_create(self):
        pending = PendingIntent(
            intent="create_note",
            title=None,
            date=None,
            time=None,
            content=None,
        )
        with patch(
            "app.services.assistant.handlers.notes.detect_intent",
            return_value={"title": "groceries", "content": "buy milk"},
        ):
            response = notes_handler.handle_pending("Just do it", pending)

        self.assertIsNotNone(response)
        self.assertIn("Review Note", response.answer)


if __name__ == "__main__":
    unittest.main()
