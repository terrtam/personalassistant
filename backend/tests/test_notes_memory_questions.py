import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.assistant.orchestrator import handle_ask
from app.services.assistant.schemas import AskRequest, AskResponse


class NotesMemoryQuestionTests(unittest.TestCase):
    def test_question_like_uses_notes_memory_when_match(self):
        payload = AskRequest(question="who is emily", k=5)
        sources = [
            {
                "text": "Instructor: Dr. Emily Carter, Email: ecarter@university.edu",
                "metadata": {"source": "note", "title": "Contact Information"},
                "score": 0.91,
            }
        ]

        with patch(
            "app.services.assistant.orchestrator.retrieve_notes_memory",
            return_value=sources,
        ) as mock_retrieve, patch(
            "app.services.assistant.orchestrator.detect_intent"
        ) as mock_detect, patch(
            "app.services.assistant.orchestrator.conversation_handler.handle_rag_from_sources",
            new_callable=AsyncMock,
        ) as mock_rag:
            mock_rag.return_value = AskResponse(
                model="assistant", answer="from sources", sources=[]
            )

            response = asyncio.run(handle_ask(payload))

            self.assertEqual(response.answer, "from sources")
            mock_retrieve.assert_called_once()
            mock_rag.assert_awaited_once()
            mock_detect.assert_not_called()

    def test_question_like_falls_back_when_no_match(self):
        payload = AskRequest(question="who is emily", k=5)

        with patch(
            "app.services.assistant.orchestrator.retrieve_notes_memory",
            return_value=[],
        ) as mock_retrieve, patch(
            "app.services.assistant.orchestrator.detect_intent",
            return_value={
                "intent": "chat",
                "title": None,
                "content": None,
                "date": None,
                "time": None,
            },
        ) as mock_detect, patch(
            "app.services.assistant.orchestrator.conversation_handler.handle_chat",
            new_callable=AsyncMock,
        ) as mock_chat:
            mock_chat.return_value = AskResponse(
                model="assistant", answer="fallback chat", sources=[]
            )

            response = asyncio.run(handle_ask(payload))

            self.assertEqual(response.answer, "fallback chat")
            mock_retrieve.assert_called_once()
            mock_detect.assert_called_once()
            mock_chat.assert_awaited_once()
