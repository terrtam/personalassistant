from fastapi import APIRouter
from fastapi import Query

from fastapi import HTTPException

from app.services import notes_service
from app.services.notes_service import CreateNoteRequest, Note, UpdateNoteRequest

router = APIRouter(prefix="/notes", tags=["notes"])


@router.get("", response_model=list[Note])
async def list_notes() -> list[Note]:
    return notes_service.list_notes()


@router.post("", response_model=Note, status_code=201)
async def create_note(payload: CreateNoteRequest) -> Note:
    return notes_service.create_note(payload)


@router.put("/{note_id}", response_model=Note)
async def update_note(note_id: str, payload: UpdateNoteRequest) -> Note:
    try:
        return notes_service.update_note(note_id, payload)
    except ValueError as exc:
        detail = str(exc)
        status = 400 if "Nothing to update" in detail else 404
        raise HTTPException(status_code=status, detail=detail) from exc


@router.delete("/{note_id}", response_model=Note)
async def delete_note(
    note_id: str,
    confirm: bool = Query(default=False, description="Set true to confirm deletion."),
) -> Note:
    if not confirm:
        raise HTTPException(
            status_code=409,
            detail="Deletion requires confirmation. Retry with ?confirm=true.",
        )
    try:
        return notes_service.delete_note(note_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
