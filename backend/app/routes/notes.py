from datetime import datetime, UTC
from threading import Lock
from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/notes", tags=["notes"])

_notes: list["Note"] = []
_notes_lock = Lock()


class CreateNoteRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    content: str = Field(..., min_length=1, max_length=5000)


class Note(BaseModel):
    id: str
    title: str
    content: str
    created_at: datetime


@router.get("", response_model=list[Note])
async def list_notes() -> list[Note]:
    with _notes_lock:
        return list(_notes)


@router.post("", response_model=Note, status_code=201)
async def create_note(payload: CreateNoteRequest) -> Note:
    note = Note(
        id=str(uuid4()),
        title=payload.title.strip(),
        content=payload.content.strip(),
        created_at=datetime.now(UTC),
    )
    with _notes_lock:
        _notes.append(note)
    return note
