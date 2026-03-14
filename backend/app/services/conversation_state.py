from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from threading import Lock


@dataclass
class PendingIntent:
    intent: str
    title: str | None
    date: str | None
    time: str | None
    content: str | None = None
    new_title: str | None = None
    note_field: str | None = None
    duration_minutes: int | None = None
    selection: list[dict[str, Any]] | None = None
    target: dict[str, Any] | None = None
    awaiting_confirmation: bool = False
    bulk_notes: list[dict[str, Any]] | None = None
    note_index: int | None = None
    awaiting_note_confirmation: bool = False
    saved_notes: list[str] | None = None
    skipped_notes: list[str] | None = None
    bulk_events: list[dict[str, Any]] | None = None
    event_index: int | None = None
    awaiting_event_details: bool = False
    awaiting_bulk_event_confirmation: bool = False
    last_attachment_text: str | None = None
    last_attachment_filenames: list[str] | None = None


_pending: PendingIntent | None = None
_attachment_cache: dict[str, Any] = {}
_lock = Lock()


def get_pending() -> PendingIntent | None:
    with _lock:
        return _pending


def set_pending(pending: PendingIntent) -> None:
    global _pending
    with _lock:
        _pending = pending


def clear_pending() -> None:
    global _pending
    with _lock:
        _pending = None


def get_attachment_cache() -> dict[str, Any]:
    with _lock:
        return dict(_attachment_cache)


def set_attachment_cache(text: str | None, filenames: list[str] | None) -> None:
    with _lock:
        if text:
            _attachment_cache["text"] = text
        if filenames:
            _attachment_cache["filenames"] = list(filenames)
