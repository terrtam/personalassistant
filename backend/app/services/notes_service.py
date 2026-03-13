"""
In-memory notes service.

Defines data models and basic CRUD operations for notes, including
creation, retrieval, searching, updating, and deletion. Notes are
stored in a thread-safe in-memory list.
"""

from datetime import UTC, datetime
from threading import Lock
from uuid import uuid4

from pydantic import BaseModel, Field

_notes: list["Note"] = []
_notes_lock = Lock()


class CreateNoteRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    content: str = Field(..., min_length=1, max_length=5000)


class UpdateNoteRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    content: str | None = Field(default=None, min_length=1, max_length=5000)


class Note(BaseModel):
    id: str
    title: str
    content: str
    created_at: datetime


def list_notes() -> list[Note]:
    with _notes_lock:
        return list(_notes)


def create_note(payload: CreateNoteRequest) -> Note:
    note = Note(
        id=str(uuid4()),
        title=payload.title.strip(),
        content=payload.content.strip(),
        created_at=datetime.now(UTC),
    )
    with _notes_lock:
        _notes.append(note)
    return note


def search_notes(query: str) -> list[Note]:
    if not query:
        return list_notes()
    query_lower = query.strip().lower()
    if not query_lower:
        return list_notes()
    with _notes_lock:
        notes = list(_notes)
    return [
        note
        for note in notes
        if query_lower in note.title.lower() or query_lower in note.content.lower()
    ]


def update_note(note_id: str, payload: UpdateNoteRequest) -> Note:
    if not note_id:
        raise ValueError("note_id is required.")
    updates: dict[str, str] = {}
    if payload.title:
        updates["title"] = payload.title.strip()
    if payload.content:
        updates["content"] = payload.content.strip()
    if not updates:
        raise ValueError("Nothing to update.")

    with _notes_lock:
        for index, note in enumerate(_notes):
            if note.id == note_id:
                updated = _copy_note(note, updates)
                _notes[index] = updated
                return updated

    raise ValueError("Note not found.")


def delete_note(note_id: str) -> Note:
    if not note_id:
        raise ValueError("note_id is required.")
    with _notes_lock:
        for index, note in enumerate(_notes):
            if note.id == note_id:
                removed = _notes.pop(index)
                return removed
    raise ValueError("Note not found.")


def _copy_note(note: Note, updates: dict[str, str]) -> Note:
    if hasattr(note, "model_copy"):
        return note.model_copy(update=updates)
    return note.copy(update=updates)
