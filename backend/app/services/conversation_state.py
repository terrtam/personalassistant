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


_pending: PendingIntent | None = None
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
