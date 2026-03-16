"""
SQLite-backed notes service.

Defines data models and basic CRUD operations for notes, including
creation, retrieval, searching, updating, and deletion. Notes are
stored in a thread-safe SQLite database.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from uuid import uuid4

from pydantic import BaseModel, Field

from app.core.settings import get_settings

_notes_lock = Lock()
_db_initialized = False


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
    _ensure_db()
    with _notes_lock:
        conn = _get_connection()
        rows = conn.execute(
            "SELECT id, title, content, created_at FROM notes ORDER BY created_at DESC"
        ).fetchall()
    return [_row_to_note(row) for row in rows]


def create_note(payload: CreateNoteRequest) -> Note:
    _ensure_db()
    note = Note(
        id=str(uuid4()),
        title=payload.title.strip(),
        content=payload.content.strip(),
        created_at=datetime.now(UTC),
    )
    with _notes_lock:
        conn = _get_connection()
        conn.execute(
            "INSERT INTO notes (id, title, content, created_at) VALUES (?, ?, ?, ?)",
            (note.id, note.title, note.content, note.created_at.isoformat()),
        )
        conn.commit()
    return note


def search_notes(query: str) -> list[Note]:
    _ensure_db()
    if not query:
        return list_notes()
    query_lower = query.strip().lower()
    if not query_lower:
        return list_notes()
    pattern = f"%{query_lower}%"
    with _notes_lock:
        conn = _get_connection()
        rows = conn.execute(
            """
            SELECT id, title, content, created_at
            FROM notes
            WHERE lower(title) LIKE ? OR lower(content) LIKE ?
            ORDER BY created_at DESC
            """,
            (pattern, pattern),
        ).fetchall()
    return [_row_to_note(row) for row in rows]


def update_note(note_id: str, payload: UpdateNoteRequest) -> Note:
    _ensure_db()
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
        conn = _get_connection()
        row = conn.execute(
            "SELECT id, title, content, created_at FROM notes WHERE id = ?",
            (note_id,),
        ).fetchone()
        if not row:
            raise ValueError("Note not found.")
        existing = _row_to_note(row)
        updated = _copy_note(existing, updates)
        conn.execute(
            "UPDATE notes SET title = ?, content = ? WHERE id = ?",
            (updated.title, updated.content, note_id),
        )
        conn.commit()
        return updated

    raise ValueError("Note not found.")


def delete_note(note_id: str) -> Note:
    _ensure_db()
    if not note_id:
        raise ValueError("note_id is required.")
    with _notes_lock:
        conn = _get_connection()
        row = conn.execute(
            "SELECT id, title, content, created_at FROM notes WHERE id = ?",
            (note_id,),
        ).fetchone()
        if not row:
            raise ValueError("Note not found.")
        conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        conn.commit()
        return _row_to_note(row)
    raise ValueError("Note not found.")


def _copy_note(note: Note, updates: dict[str, str]) -> Note:
    if hasattr(note, "model_copy"):
        return note.model_copy(update=updates)
    return note.copy(update=updates)


def _row_to_note(row: sqlite3.Row) -> Note:
    created_at_raw = row["created_at"]
    created_at = (
        datetime.fromisoformat(created_at_raw)
        if isinstance(created_at_raw, str)
        else datetime.fromtimestamp(created_at_raw, UTC)
    )
    return Note(
        id=row["id"],
        title=row["title"],
        content=row["content"],
        created_at=created_at,
    )


def _get_connection() -> sqlite3.Connection:
    settings = get_settings()
    db_path = Path(settings.notes_db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_db() -> None:
    global _db_initialized
    if _db_initialized:
        return
    with _notes_lock:
        if _db_initialized:
            return
        conn = _get_connection()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
        _db_initialized = True
