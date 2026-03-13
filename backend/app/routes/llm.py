"""
LLM API router.

Defines endpoints that handle user messages and route them through the
assistant pipeline. Requests are analyzed for intent and dispatched to
the appropriate services such as calendar operations, note management,
or general conversational responses.
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from app.services.embeddings.pipeline import search_index
from app.services.intent_detection import detect_intent
from app.services.conversation_state import PendingIntent, clear_pending, get_pending, set_pending
from app.services.temporal_parser import (
    extract_date,
    extract_duration_minutes,
    extract_explicit_times,
    extract_time,
    extract_time_range,
    strip_temporal_tokens,
)
from app.services import calendar_service, notes_service
from app.services.calendar_service import (
    CalendarActionError,
    CalendarConflictError,
    CalendarDisambiguationError,
    build_delete_confirmation_message,
)
from app.services.llm.groq_client import get_groq_chat_model
from app.services.llm.prompt_templates import CHAT_PROMPT_TEMPLATE, build_rag_prompt

router = APIRouter(prefix="/llm", tags=["llm"])


class LLMSmokeRequest(BaseModel):
    prompt: str = Field(..., min_length=1)


class LLMSmokeResponse(BaseModel):
    model: str
    response: str


class AskRequest(BaseModel):
    question: str | None = Field(default=None, min_length=1)
    query: str | None = Field(default=None, min_length=1)
    k: int = Field(default=5, ge=1, le=20)

    @model_validator(mode="after")
    def _require_message(self) -> "AskRequest":
        if not (self.question or self.query):
            raise ValueError("question or query is required.")
        return self


class AskSource(BaseModel):
    text: str
    metadata: dict
    score: float


class AskResponse(BaseModel):
    model: str
    answer: str
    sources: list[AskSource]


def _build_missing_details_message(
    intent: str,
    title: str | None,
    missing_title: bool,
    missing_date: bool,
    missing_time: bool,
    missing_duration: bool,
) -> str:
    event_label = f'"{title}"' if title else "the event"
    missing_parts: list[str] = []
    if missing_title:
        missing_parts.append("**Title**")
    if missing_date:
        missing_parts.append("**Date**")
    if missing_time:
        missing_parts.append("**Time**")
    if missing_duration:
        missing_parts.append("**End Time / Duration**")
    header = "**Missing Details**"
    bullets = "\n".join(f"- {part}" for part in missing_parts) if missing_parts else ""
    question = "Could you share the remaining event details?"
    if intent == "create_event":
        if missing_title and missing_date and missing_time:
            question = "What should I call the event, and what date/time should I schedule it?"
        if missing_duration and not (missing_title or missing_date or missing_time):
            question = "When should it end? (You can also say a duration like 45 minutes.)"
        if missing_title and missing_date:
            question = "What should I call the event, and what date should I schedule it?"
        if missing_title and missing_time:
            question = "What should I call the event, and what time should I schedule it?"
        if missing_title:
            question = "What should I call the event?"
        if missing_date and missing_time:
            question = f"What date and time should I schedule {event_label}?"
        if missing_date:
            question = f"What date should I schedule {event_label}?"
        if missing_time:
            question = f"What time should I schedule {event_label}?"
        if missing_duration and (missing_title or missing_date or missing_time):
            question = f"{question} Also, when should it end? (Or say a duration.)"
    if intent == "update_event":
        if missing_title and missing_date and missing_time:
            question = "Which event should I move, and what date/time should I move it to?"
        if missing_title and missing_date:
            question = "Which event should I move, and what date should I move it to?"
        if missing_title and missing_time:
            question = "Which event should I move, and what time should I move it to?"
        if missing_title:
            question = "Which event should I move?"
        if missing_date and missing_time:
            question = f"What date and time should I move {event_label} to?"
        if missing_date:
            question = f"What date should I move {event_label} to?"
        if missing_time:
            question = f"What time should I move {event_label} to?"
    if intent == "delete_event":
        if missing_title and missing_date and missing_time:
            question = "Which event should I cancel, and what date/time is it?"
        if missing_title and missing_date:
            question = "Which event should I cancel, and what date is it?"
        if missing_title and missing_time:
            question = "Which event should I cancel, and what time is it?"
        if missing_title:
            question = "Which event should I cancel?"
        if missing_date and missing_time:
            question = f"What date and time is {event_label}?"
        if missing_date:
            question = f"What date is {event_label}?"
        if missing_time:
            question = f"What time is {event_label}?"
    if bullets:
        return f"{header}\n{bullets}\n\n{question}"
    return f"{header}\n\n{question}"


def _extract_selection_index(message: str, max_index: int) -> int | None:
    import re

    match = re.search(r"\b(\d{1,2})\b", message)
    if not match:
        return None
    value = int(match.group(1))
    if 1 <= value <= max_index:
        return value
    return None


def _extract_selection_by_id(
    message: str, candidates: list[dict[str, object]]
) -> dict[str, object] | None:
    lowered = message.strip().lower()
    if not lowered:
        return None
    for candidate in candidates:
        event_id = str(candidate.get("id") or "")
        if not event_id:
            continue
        short_id = event_id[-6:].lower()
        if short_id and short_id in lowered:
            return candidate
        if event_id.lower() in lowered:
            return candidate
    return None


def _build_ambiguous_time_message(parsed_time: str | None) -> str:
    if parsed_time:
        try:
            hour = int(parsed_time.split(":")[0])
            hour = 12 if hour % 12 == 0 else hour % 12
            return (
                "**Clarification Needed**\n"
                f"- Did you mean `{hour}am` or `{hour}pm`?"
            )
        except ValueError:
            pass
    return (
        "**Clarification Needed**\n"
        "- Please specify a time with AM/PM, like `4pm` or `4:30pm`."
    )


def _extract_notes_query(message: str) -> str | None:
    import re

    lowered = message.strip().lower()
    if not lowered:
        return None
    patterns = [
        r"\bnotes?\s+(?:about|on|regarding)\s+(.+)$",
        r"\bnotes?\s+for\s+(.+)$",
        r"\bnote\s+about\s+(.+)$",
        r"\bfind\s+my\s+notes?\s+(?:about|on|regarding)\s+(.+)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            candidate = match.group(1).strip(" ?.")
            return candidate or None
    return None


def _is_notes_query(message: str) -> bool:
    lowered = message.strip().lower()
    if not lowered:
        return False
    if _extract_notes_query(message):
        return True
    if lowered in {"notes", "my notes"}:
        return True
    query_markers = [
        "what",
        "show",
        "list",
        "view",
        "see",
        "do i have",
        "any",
    ]
    return ("note" in lowered or "notes" in lowered) and any(
        marker in lowered for marker in query_markers
    )


def _is_notes_create(message: str) -> bool:
    lowered = message.strip().lower()
    if not lowered:
        return False
    triggers = [
        "take a note",
        "note that",
        "note:",
        "remember to",
        "remember",
        "remind me to",
        "jot down",
        "write down",
        "save a note",
    ]
    return any(trigger in lowered for trigger in triggers)


def _is_notes_update(message: str) -> bool:
    lowered = message.strip().lower()
    if not lowered:
        return False
    return "note" in lowered and any(
        trigger in lowered
        for trigger in ["update", "edit", "change", "revise", "rename", "title", "name"]
    )


def _is_notes_delete(message: str) -> bool:
    lowered = message.strip().lower()
    if not lowered:
        return False
    return "note" in lowered and any(
        trigger in lowered for trigger in ["delete", "remove", "discard", "erase"]
    )


def _extract_note_content(message: str, intent: str | None = None) -> str | None:
    import re

    if not message:
        return None
    patterns: list[re.Pattern[str]] = []
    if intent in {None, "create_note"}:
        patterns.extend(
            [
                re.compile(
                    r"^\s*(?:take a note|note|note that|remember to|remember|remind me to|jot down|write down)\s*[:\-]?\s*(.+)$",
                    re.IGNORECASE,
                ),
                re.compile(r"^\s*note\s*[:\-]\s*(.+)$", re.IGNORECASE),
            ]
        )
    if intent == "update_note":
        patterns.extend(
            [
                re.compile(
                    r"\b(?:update|edit|change|revise)\b.*?\bnote\b\s*(?:to|with|as|:)\s*(.+)$",
                    re.IGNORECASE,
                ),
                re.compile(
                    r"\b(?:update|edit|change|revise)\b.*?\bto\b\s+(.+)$",
                    re.IGNORECASE,
                ),
            ]
        )

    for pattern in patterns:
        match = pattern.search(message)
        if match:
            content = match.group(1).strip()
            return content or None

    if intent == "create_note":
        stripped = message.strip()
        return stripped or None
    return None


def _wants_note_rename(message: str) -> bool:
    lowered = message.strip().lower()
    if not lowered:
        return False
    return (
        "rename" in lowered
        or "note title" in lowered
        or "note name" in lowered
        or ("title" in lowered and "note" in lowered)
        or ("name" in lowered and "note" in lowered)
    )


def _extract_note_new_title(message: str) -> str | None:
    import re

    if not message:
        return None
    patterns = [
        re.compile(r"\brename\b.*?\bto\b\s+(.+)$", re.IGNORECASE),
        re.compile(r"\brename\b.*?\bas\b\s+(.+)$", re.IGNORECASE),
        re.compile(
            r"\b(?:change|edit|update)\b.*?\b(?:title|name)\b\s+(?:to|as)\s+(.+)$",
            re.IGNORECASE,
        ),
        re.compile(r"\b(?:title|name)\b\s+(?:to|as)\s+(.+)$", re.IGNORECASE),
    ]
    for pattern in patterns:
        match = pattern.search(message)
        if match:
            candidate = match.group(1).strip(" ?.")
            return candidate or None
    return None


def _extract_note_update_payload(message: str) -> tuple[str | None, str | None]:
    new_title = _extract_note_new_title(message)
    content = _extract_note_content(message, "update_note")
    if not content and not new_title:
        stripped = message.strip()
        content = stripped or None
    return new_title, content


def _extract_note_title_candidate(message: str, intent: str) -> str | None:
    import re

    if not message:
        return None
    if intent == "update_note":
        pattern = re.compile(
            r"\b(?:update|edit|change|revise|rename)\b\s+(.*?)\s+(?:note|notes)\b",
            re.IGNORECASE,
        )
    elif intent == "delete_note":
        pattern = re.compile(
            r"\b(?:delete|remove|discard)\b\s+(.*?)\s+(?:note|notes)\b",
            re.IGNORECASE,
        )
    else:
        return None
    match = pattern.search(message)
    if not match:
        return None
    candidate = match.group(1)
    cleaned = re.sub(r"\b(my|the|that|this)\b", " ", candidate, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,")
    return cleaned or None


def _derive_note_title(content: str) -> str:
    cleaned = " ".join(content.strip().split())
    if not cleaned:
        return "Note"
    sentence = cleaned.split(".")[0]
    words = sentence.split()
    title = " ".join(words[:6])
    return title[:60].rstrip()


def _note_candidates_from_notes(
    notes: list[notes_service.Note],
) -> list[dict[str, object]]:
    notes_sorted = sorted(notes, key=lambda note: note.created_at, reverse=True)
    return [
        {
            "id": note.id,
            "title": note.title,
            "content": note.content,
            "created_at": note.created_at,
        }
        for note in notes_sorted
    ]


def _format_note_choice(index: int, candidate: dict[str, object]) -> str:
    title = str(candidate.get("title") or "Untitled").strip()
    content = " ".join(str(candidate.get("content") or "").split())
    if len(content) > 120:
        content = f"{content[:117]}..."
    created = candidate.get("created_at")
    if isinstance(created, datetime):
        created_str = created.astimezone().strftime("%a %b %d, %Y")
    else:
        created_str = str(created) if created else "unknown date"
    note_id = str(candidate.get("id") or "")
    short_id = note_id[-6:] if note_id else "unknown"
    return f"{index}) **{title}** - {content} (_{created_str}_) (id: `{short_id}`)"


def _build_note_disambiguation_message(
    query: str, candidates: list[dict[str, object]]
) -> str:
    header = f'**Multiple Notes Found**\nMatches for "{query}":'
    lines = [header, "Reply with the number or the id shown."]
    for idx, candidate in enumerate(candidates, start=1):
        lines.append(_format_note_choice(idx, candidate))
    return "\n".join(lines)


def _build_note_delete_confirmation(candidate: dict[str, object]) -> str:
    title = str(candidate.get("title") or "Untitled").strip()
    content = " ".join(str(candidate.get("content") or "").split())
    if len(content) > 120:
        content = f"{content[:117]}..."
    created = candidate.get("created_at")
    if isinstance(created, datetime):
        created_str = created.astimezone().strftime("%a %b %d, %Y")
    else:
        created_str = str(created) if created else "unknown date"
    return (
        "**Confirm Delete**\n"
        f"- **Title:** {title}\n"
        f"- **Snippet:** {content}\n"
        f"- **Created:** _{created_str}_\n\n"
        "Reply `yes` to confirm or `no` to cancel."
    )


def _format_notes_list(notes: list[notes_service.Note], query: str | None = None) -> str:
    if not notes:
        if query:
            return f'**Notes**\n- _No notes found for "{query}"._'
        return "**Notes**\n- _No notes yet._"
    notes_sorted = sorted(notes, key=lambda note: note.created_at, reverse=True)
    lines = ["**Notes**"]
    for note in notes_sorted:
        title = (note.title or "Untitled").strip()
        content = " ".join((note.content or "").split())
        if len(content) > 200:
            content = f"{content[:197]}..."
        created = note.created_at.astimezone().strftime("%a %b %d, %Y")
        lines.append(f"- **{title}**: {content} (_{created}_)")
    return "\n".join(lines)


def _extract_title_candidate(message: str, intent: str | None) -> str | None:
    import re

    if not message:
        return None

    patterns: list[re.Pattern[str]] = []
    if intent == "update_event":
        patterns = [
            re.compile(
                r"\b(change|move|reschedule|update|shift|push)\b\s+(.*?)\s+\b(to|for|on|at)\b",
                re.IGNORECASE,
            )
        ]
    elif intent == "delete_event":
        patterns = [
            re.compile(
                r"\b(cancel|delete|remove)\b\s+(.*)",
                re.IGNORECASE,
            )
        ]
    elif intent == "create_event":
        patterns = [
            re.compile(
                r"\b(schedule|add|create|book|set up)\b\s+(.*)",
                re.IGNORECASE,
            )
        ]

    for pattern in patterns:
        match = pattern.search(message)
        if match:
            candidate = match.group(2)
            cleaned = strip_temporal_tokens(candidate)
            cleaned = re.sub(r"\b(to|for|on|at)\b", " ", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,")
            return cleaned or None

    return None


def _parse_confirmation(message: str) -> bool | None:
    lowered = message.strip().lower()
    if not lowered:
        return None
    if lowered in {"yes", "y", "confirm", "sure", "ok", "okay"}:
        return True
    if lowered in {"no", "n", "cancel", "stop"}:
        return False
    return None


def _duration_from_end_time(date_str: str, start_time: str, end_time: str) -> int | None:
    try:
        start_date = datetime.fromisoformat(date_str).date()
    except ValueError:
        return None
    try:
        start_t = datetime.strptime(start_time, "%H:%M").time()
        end_t = datetime.strptime(end_time, "%H:%M").time()
    except ValueError:
        return None
    tzinfo = datetime.now().astimezone().tzinfo
    start_dt = datetime.combine(start_date, start_t, tzinfo=tzinfo)
    end_dt = datetime.combine(start_date, end_t, tzinfo=tzinfo)
    if end_dt <= start_dt:
        return None
    return int((end_dt - start_dt).total_seconds() // 60)


def _duration_between_times(start_time: str, end_time: str) -> int | None:
    try:
        start_t = datetime.strptime(start_time, "%H:%M").time()
        end_t = datetime.strptime(end_time, "%H:%M").time()
    except ValueError:
        return None
    base_date = datetime.now().date()
    tzinfo = datetime.now().astimezone().tzinfo
    start_dt = datetime.combine(base_date, start_t, tzinfo=tzinfo)
    end_dt = datetime.combine(base_date, end_t, tzinfo=tzinfo)
    if end_dt <= start_dt:
        end_dt = end_dt + timedelta(days=1)
    return int((end_dt - start_dt).total_seconds() // 60)




@router.post("/smoke", response_model=LLMSmokeResponse)
async def smoke_test_llm(payload: LLMSmokeRequest) -> LLMSmokeResponse:
    try:
        clear_pending()
        llm = get_groq_chat_model()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Groq configuration error: {str(exc)}",
        ) from exc

    try:
        result = await llm.ainvoke(payload.prompt)
        content = result.content if hasattr(result, "content") else str(result)
        if isinstance(content, list):
            content = " ".join(str(item) for item in content)
        return LLMSmokeResponse(model=llm.model_name, response=str(content))
    except Exception as exc:
        message = str(exc).lower()
        status = 503 if any(token in message for token in ["timeout", "temporar", "unavailable", "rate limit", "overloaded"]) else 502
        raise HTTPException(
            status_code=status,
            detail="Groq provider request failed. Check API key, model, and network connectivity.",
        ) from exc


@router.post("/ask", response_model=AskResponse)
async def ask_question(payload: AskRequest) -> AskResponse:
    message = payload.query or payload.question or ""
    pending = get_pending()
    if pending is not None:
        if pending.intent in {"create_note", "update_note", "delete_note"}:
            if pending.awaiting_confirmation and pending.intent == "delete_note":
                decision = _parse_confirmation(message)
                if decision is None:
                    return AskResponse(
                        model="notes",
                        answer="**Confirmation Needed**\n- Reply `yes` to delete or `no` to cancel.",
                        sources=[],
                    )
                if decision:
                    clear_pending()
                    if not pending.target:
                        return AskResponse(
                            model="notes",
                            answer="I couldn't find that note anymore.",
                            sources=[],
                        )
                    try:
                        removed = notes_service.delete_note(str(pending.target.get("id")))
                    except ValueError as exc:
                        return AskResponse(model="notes", answer=str(exc), sources=[])
                    return AskResponse(
                        model="notes",
                        answer=f'**Note Deleted**\n- **Title:** {removed.title}',
                        sources=[],
                    )
                clear_pending()
                return AskResponse(
                    model="notes",
                    answer="Okay, I won't delete it.",
                    sources=[],
                )
            if pending.selection:
                index = _extract_selection_index(message, len(pending.selection))
                selected = None
                if index is not None:
                    selected = pending.selection[index - 1]
                else:
                    selected = _extract_selection_by_id(message, pending.selection)

                if selected:
                    if pending.intent == "delete_note":
                        set_pending(
                            PendingIntent(
                                intent=pending.intent,
                                title=pending.title,
                                date=None,
                                time=None,
                                content=pending.content,
                                new_title=pending.new_title,
                                target=selected,
                                awaiting_confirmation=True,
                            )
                        )
                        return AskResponse(
                            model="notes",
                            answer=_build_note_delete_confirmation(selected),
                            sources=[],
                        )
                    if pending.intent == "update_note":
                        if pending.note_field == "title":
                            new_title = pending.new_title
                            if not new_title:
                                set_pending(
                                    PendingIntent(
                                        intent=pending.intent,
                                        title=pending.title,
                                        date=None,
                                        time=None,
                                        content=pending.content,
                                        new_title=None,
                                        note_field="title",
                                        target=selected,
                                    )
                                )
                                return AskResponse(
                                    model="notes",
                                    answer="**Missing Details**\n- **Title**\n\nWhat should the new title be?",
                                    sources=[],
                                )
                            clear_pending()
                            try:
                                updated = notes_service.update_note(
                                    str(selected.get("id")),
                                    notes_service.UpdateNoteRequest(title=new_title),
                                )
                            except ValueError as exc:
                                return AskResponse(model="notes", answer=str(exc), sources=[])
                            return AskResponse(
                                model="notes",
                                answer=(
                                    "**Note Updated**\n"
                                    f"- **Title:** {updated.title}\n"
                                    f"- **Content:** {updated.content}"
                                ),
                                sources=[],
                            )
                        new_title, content = pending.new_title, pending.content
                        if not content and not new_title:
                            set_pending(
                                PendingIntent(
                                    intent=pending.intent,
                                    title=pending.title,
                                    date=None,
                                    time=None,
                                    content=None,
                                    new_title=None,
                                    note_field="content",
                                    target=selected,
                                )
                            )
                            return AskResponse(
                                model="notes",
                                answer="**Missing Details**\n- **Content**\n\nWhat should the note say?",
                                sources=[],
                            )
                        clear_pending()
                        try:
                            updated = notes_service.update_note(
                                str(selected.get("id")),
                                notes_service.UpdateNoteRequest(
                                    title=new_title, content=content
                                ),
                            )
                        except ValueError as exc:
                            return AskResponse(model="notes", answer=str(exc), sources=[])
                        return AskResponse(
                            model="notes",
                            answer=(
                                "**Note Updated**\n"
                                f"- **Title:** {updated.title}\n"
                                f"- **Content:** {updated.content}"
                            ),
                            sources=[],
                        )

                return AskResponse(
                    model="notes",
                    answer="**Selection Needed**\n- Please reply with the number or the id shown above.",
                    sources=[],
                )

            if pending.target:
                if pending.intent == "delete_note":
                    set_pending(
                        PendingIntent(
                            intent=pending.intent,
                            title=pending.title,
                            date=None,
                            time=None,
                            content=pending.content,
                            new_title=pending.new_title,
                            target=pending.target,
                            awaiting_confirmation=True,
                        )
                    )
                    return AskResponse(
                        model="notes",
                        answer=_build_note_delete_confirmation(pending.target),
                        sources=[],
                    )
                if pending.intent == "update_note":
                    if pending.note_field == "title":
                        new_title = pending.new_title or _extract_note_new_title(message) or message.strip()
                        if not new_title:
                            set_pending(
                                PendingIntent(
                                    intent=pending.intent,
                                    title=pending.title,
                                    date=None,
                                    time=None,
                                    content=pending.content,
                                    new_title=None,
                                    note_field="title",
                                    target=pending.target,
                                )
                            )
                            return AskResponse(
                                model="notes",
                                answer="**Missing Details**\n- **Title**\n\nWhat should the new title be?",
                                sources=[],
                            )
                        clear_pending()
                        try:
                            updated = notes_service.update_note(
                                str(pending.target.get("id")),
                                notes_service.UpdateNoteRequest(title=new_title),
                            )
                        except ValueError as exc:
                            return AskResponse(model="notes", answer=str(exc), sources=[])
                        return AskResponse(
                            model="notes",
                            answer=(
                                "**Note Updated**\n"
                                f"- **Title:** {updated.title}\n"
                                f"- **Content:** {updated.content}"
                            ),
                            sources=[],
                        )
                    new_title, content = pending.new_title, pending.content
                    if not content and not new_title:
                        new_title, content = _extract_note_update_payload(message)
                    if not content and not new_title:
                        set_pending(
                            PendingIntent(
                                intent=pending.intent,
                                title=pending.title,
                                date=None,
                                time=None,
                                content=None,
                                new_title=None,
                                note_field="content",
                                target=pending.target,
                            )
                        )
                        return AskResponse(
                            model="notes",
                            answer="**Missing Details**\n- **Content**\n\nWhat should the note say?",
                            sources=[],
                        )
                    clear_pending()
                    try:
                        updated = notes_service.update_note(
                            str(pending.target.get("id")),
                            notes_service.UpdateNoteRequest(
                                title=new_title, content=content
                            ),
                        )
                    except ValueError as exc:
                        return AskResponse(model="notes", answer=str(exc), sources=[])
                    return AskResponse(
                        model="notes",
                        answer=(
                            "**Note Updated**\n"
                            f"- **Title:** {updated.title}\n"
                            f"- **Content:** {updated.content}"
                        ),
                        sources=[],
                    )

            if pending.intent == "create_note":
                content = pending.content or _extract_note_content(message, "create_note")
                if not content:
                    set_pending(
                        PendingIntent(
                            intent=pending.intent,
                            title=pending.title,
                            date=None,
                            time=None,
                            content=None,
                            note_field="content",
                        )
                    )
                    return AskResponse(
                        model="notes",
                        answer="**Missing Details**\n- **Content**\n\nWhat should the note say?",
                        sources=[],
                    )
                title = pending.title or _derive_note_title(content)
                clear_pending()
                note = notes_service.create_note(
                    notes_service.CreateNoteRequest(title=title, content=content)
                )
                return AskResponse(
                    model="notes",
                    answer=(
                        "**Note Saved**\n"
                        f"- **Title:** {note.title}\n"
                        f"- **Content:** {note.content}"
                    ),
                    sources=[],
                )

            if pending.intent in {"update_note", "delete_note"}:
                query = (
                    pending.title
                    or _extract_note_title_candidate(message, pending.intent)
                    or _extract_notes_query(message)
                    or message.strip()
                )
                if not query:
                    return AskResponse(
                        model="notes",
                        answer="Which note did you mean?",
                        sources=[],
                    )
                candidates_notes = notes_service.search_notes(query)
                candidates = _note_candidates_from_notes(candidates_notes)
                if not candidates:
                    clear_pending()
                    return AskResponse(
                        model="notes",
                        answer=f'I could not find any notes matching "{query}".',
                        sources=[],
                    )
                if len(candidates) > 1:
                    set_pending(
                        PendingIntent(
                            intent=pending.intent,
                            title=query,
                            date=None,
                            time=None,
                            content=pending.content,
                            new_title=pending.new_title,
                            note_field=pending.note_field,
                            selection=candidates,
                        )
                    )
                    return AskResponse(
                        model="notes",
                        answer=_build_note_disambiguation_message(query, candidates),
                        sources=[],
                    )
                target = candidates[0]
                if pending.intent == "delete_note":
                    set_pending(
                        PendingIntent(
                            intent=pending.intent,
                            title=query,
                            date=None,
                            time=None,
                            content=pending.content,
                            new_title=pending.new_title,
                            target=target,
                            awaiting_confirmation=True,
                        )
                    )
                    return AskResponse(
                        model="notes",
                        answer=_build_note_delete_confirmation(target),
                        sources=[],
                    )
                new_title, content = pending.new_title, pending.content
                if not content and not new_title:
                    new_title, content = _extract_note_update_payload(message)
                if not content and not new_title:
                    note_field = "title" if _wants_note_rename(message) else "content"
                    set_pending(
                        PendingIntent(
                            intent=pending.intent,
                            title=query,
                            date=None,
                            time=None,
                            content=None,
                            new_title=None,
                            note_field=note_field,
                            target=target,
                        )
                    )
                    if note_field == "title":
                        prompt = "**Missing Details**\n- **Title**\n\nWhat should the new title be?"
                    else:
                        prompt = "**Missing Details**\n- **Content**\n\nWhat should the note say?"
                    return AskResponse(model="notes", answer=prompt, sources=[])
                clear_pending()
                try:
                    updated = notes_service.update_note(
                        str(target.get("id")),
                        notes_service.UpdateNoteRequest(
                            title=new_title, content=content
                        ),
                    )
                except ValueError as exc:
                    return AskResponse(model="notes", answer=str(exc), sources=[])
                return AskResponse(
                    model="notes",
                    answer=(
                        "**Note Updated**\n"
                        f"- **Title:** {updated.title}\n"
                        f"- **Content:** {updated.content}"
                    ),
                    sources=[],
                )
        if pending.awaiting_confirmation and pending.intent == "delete_event":
            decision = _parse_confirmation(message)
            if decision is None:
                return AskResponse(
                    model="calendar",
                    answer="**Confirmation Needed**\n- Reply `yes` to delete or `no` to cancel.",
                    sources=[],
                )
            if decision:
                clear_pending()
                try:
                    answer = calendar_service.delete_event_from_candidate(pending.target)
                except CalendarActionError as exc:
                    answer = str(exc)
                return AskResponse(model="calendar", answer=answer, sources=[])
            clear_pending()
            return AskResponse(
                model="calendar",
                answer="Okay, I won't delete it.",
                sources=[],
            )
        if pending.target:
            parsed_date = extract_date(message)
            range_start, range_end, range_ambiguous = extract_time_range(message)
            parsed_time, time_ambiguous = extract_time(message)
            if range_ambiguous:
                return AskResponse(
                    model="calendar",
                    answer=_build_ambiguous_time_message(None),
                    sources=[],
                )
            if range_start and range_end:
                parsed_time = range_start
                time_ambiguous = False
            if time_ambiguous:
                return AskResponse(
                    model="calendar",
                    answer=_build_ambiguous_time_message(parsed_time),
                    sources=[],
                )

            merged_date = parsed_date or pending.date
            merged_time = parsed_time or pending.time
            if pending.intent == "update_event":
                if merged_date and merged_time:
                    clear_pending()
                    try:
                        answer = calendar_service.update_event_from_candidate(
                            pending.target, merged_date, merged_time
                        )
                    except CalendarConflictError as exc:
                        set_pending(
                            PendingIntent(
                                intent=pending.intent,
                                title=pending.title,
                                date=merged_date,
                                time=merged_time,
                                duration_minutes=pending.duration_minutes,
                                target=pending.target,
                            )
                        )
                        return AskResponse(model="calendar", answer=str(exc), sources=[])
                    except CalendarActionError as exc:
                        answer = str(exc)
                    return AskResponse(model="calendar", answer=answer, sources=[])

                set_pending(
                    PendingIntent(
                        intent=pending.intent,
                        title=pending.title,
                        date=merged_date,
                        time=merged_time,
                        duration_minutes=pending.duration_minutes,
                        target=pending.target,
                    )
                )
                return AskResponse(
                    model="calendar",
                    answer=_build_missing_details_message(
                        intent=pending.intent,
                        title=pending.title,
                        missing_title=pending.title is None,
                        missing_date=merged_date is None,
                        missing_time=merged_time is None,
                        missing_duration=False,
                    ),
                    sources=[],
                )

        if pending.selection:
            index = _extract_selection_index(message, len(pending.selection))
            selected = None
            if index is not None:
                selected = pending.selection[index - 1]
            else:
                selected = _extract_selection_by_id(message, pending.selection)

            if selected:
                clear_pending()
                if pending.intent == "update_event":
                    if not (pending.date and pending.time):
                        set_pending(
                            PendingIntent(
                                intent=pending.intent,
                                title=pending.title,
                                date=pending.date,
                                time=pending.time,
                                duration_minutes=pending.duration_minutes,
                                target=selected,
                            )
                        )
                        return AskResponse(
                            model="calendar",
                            answer=_build_missing_details_message(
                                intent=pending.intent,
                                title=pending.title,
                                missing_title=pending.title is None,
                                missing_date=pending.date is None,
                                missing_time=pending.time is None,
                                missing_duration=False,
                            ),
                            sources=[],
                        )
                    try:
                        answer = calendar_service.update_event_from_candidate(
                            selected, pending.date, pending.time
                        )
                    except CalendarConflictError as exc:
                        set_pending(
                            PendingIntent(
                                intent=pending.intent,
                                title=pending.title,
                                date=pending.date,
                                time=pending.time,
                                duration_minutes=pending.duration_minutes,
                                target=selected,
                            )
                        )
                        return AskResponse(model="calendar", answer=str(exc), sources=[])
                    except CalendarActionError as exc:
                        answer = str(exc)
                    return AskResponse(model="calendar", answer=answer, sources=[])
                if pending.intent == "delete_event":
                    set_pending(
                        PendingIntent(
                            intent=pending.intent,
                            title=pending.title,
                            date=pending.date,
                            time=pending.time,
                            duration_minutes=pending.duration_minutes,
                            target=selected,
                            awaiting_confirmation=True,
                        )
                    )
                    return AskResponse(
                        model="calendar",
                        answer=build_delete_confirmation_message(selected),
                        sources=[],
                    )

            return AskResponse(
                model="calendar",
                answer="**Selection Needed**\n- Please reply with the number or the id shown above.",
                sources=[],
            )

        parsed_date = extract_date(message)
        range_start, range_end, range_ambiguous = extract_time_range(message)
        parsed_time, time_ambiguous = extract_time(message)
        if range_ambiguous:
            return AskResponse(
                model="calendar",
                answer=_build_ambiguous_time_message(None),
                sources=[],
            )
        if range_start and range_end:
            parsed_time = range_start
            time_ambiguous = False
        if time_ambiguous:
            return AskResponse(
                model="calendar",
                answer=_build_ambiguous_time_message(parsed_time),
                sources=[],
            )
        parsed_duration = extract_duration_minutes(message)
        if parsed_duration is None and range_start and range_end:
            parsed_duration = _duration_between_times(range_start, range_end)
        if (
            pending.intent == "create_event"
            and pending.date
            and pending.time
            and pending.duration_minutes is None
            and parsed_duration is None
            and parsed_time
        ):
            inferred_duration = _duration_from_end_time(
                pending.date, pending.time, parsed_time
            )
            if inferred_duration is None:
                return AskResponse(
                    model="calendar",
                    answer="**Clarification Needed**\n- What time should the event end? (It should be after the start time.)",
                    sources=[],
                )
            parsed_duration = inferred_duration
            parsed_time = None

        title_candidate = None
        if pending.title is None:
            candidate = _extract_title_candidate(message, pending.intent)
            if candidate:
                title_candidate = candidate
            else:
                stripped = strip_temporal_tokens(message)
                if stripped:
                    title_candidate = stripped

        merged_date = parsed_date or pending.date
        merged_time = parsed_time or pending.time
        merged_title = title_candidate or pending.title
        merged_duration = parsed_duration or pending.duration_minutes

        if merged_title or merged_date or merged_time or merged_duration is not None:
            if merged_title and merged_date and merged_time and (
                pending.intent != "create_event" or merged_duration is not None
            ):
                clear_pending()
                intent = pending.intent
                if intent == "create_event":
                    try:
                        answer = calendar_service.create_event(
                            merged_title, merged_date, merged_time, merged_duration
                        )
                    except CalendarConflictError as exc:
                        set_pending(
                            PendingIntent(
                                intent=intent,
                                title=merged_title,
                                date=merged_date,
                                time=merged_time,
                                duration_minutes=merged_duration,
                            )
                        )
                        return AskResponse(model="calendar", answer=str(exc), sources=[])
                    except CalendarActionError as exc:
                        answer = str(exc)
                    return AskResponse(model="calendar", answer=answer, sources=[])
                if intent == "update_event":
                    try:
                        answer = calendar_service.update_event(
                            merged_title, merged_date, merged_time
                        )
                    except CalendarConflictError as exc:
                        set_pending(
                            PendingIntent(
                                intent=intent,
                                title=merged_title,
                                date=merged_date,
                                time=merged_time,
                                duration_minutes=merged_duration,
                            )
                        )
                        return AskResponse(model="calendar", answer=str(exc), sources=[])
                    except CalendarDisambiguationError as exc:
                        set_pending(
                            PendingIntent(
                                intent=intent,
                                title=merged_title,
                                date=merged_date,
                                time=merged_time,
                                duration_minutes=merged_duration,
                                selection=exc.candidates,
                            )
                        )
                        return AskResponse(model="calendar", answer=str(exc), sources=[])
                    except CalendarActionError as exc:
                        answer = str(exc)
                    return AskResponse(model="calendar", answer=answer, sources=[])
                if intent == "delete_event":
                    try:
                        answer = calendar_service.delete_event(
                            merged_title, merged_date, merged_time
                        )
                    except CalendarDisambiguationError as exc:
                        set_pending(
                            PendingIntent(
                                intent=intent,
                                title=merged_title,
                                date=merged_date,
                                time=merged_time,
                                duration_minutes=merged_duration,
                                selection=exc.candidates,
                            )
                        )
                        return AskResponse(model="calendar", answer=str(exc), sources=[])
                    except CalendarActionError as exc:
                        answer = str(exc)
                    return AskResponse(model="calendar", answer=answer, sources=[])

            set_pending(
                PendingIntent(
                    intent=pending.intent,
                    title=merged_title,
                    date=merged_date,
                    time=merged_time,
                    duration_minutes=merged_duration,
                )
            )
            return AskResponse(
                model="calendar",
                answer=_build_missing_details_message(
                    intent=pending.intent,
                    title=merged_title,
                    missing_title=merged_title is None,
                    missing_date=merged_date is None,
                    missing_time=merged_time is None,
                    missing_duration=merged_duration is None
                    and pending.intent == "create_event",
                ),
                sources=[],
            )
    try:
        intent_data = detect_intent(message)
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Groq configuration error: {str(exc)}",
        ) from exc
    except Exception as exc:
        message_lower = str(exc).lower()
        status = 503 if any(token in message_lower for token in ["timeout", "temporar", "unavailable", "rate limit", "overloaded"]) else 502
        raise HTTPException(
            status_code=status,
            detail="Groq provider request failed. Check API key, model, and network connectivity.",
        ) from exc

    intent = intent_data.get("intent")
    title = intent_data.get("title")
    content = intent_data.get("content")
    date_str = intent_data.get("date")
    time_str = intent_data.get("time")
    if intent == "needs_clarification":
        clear_pending()
        return AskResponse(
            model="assistant",
            answer="Could you clarify what you'd like me to do?",
            sources=[],
        )
    if intent == "query_notes" or (intent == "chat" and _is_notes_query(message)):
        clear_pending()
        query = _extract_notes_query(message) or title
        notes = notes_service.search_notes(query) if query else notes_service.list_notes()
        return AskResponse(
            model="notes",
            answer=_format_notes_list(notes, query),
            sources=[],
        )
    if intent == "create_note" or (intent == "chat" and _is_notes_create(message)):
        intent = "create_note"
        note_content = content or _extract_note_content(message, intent)
        if not note_content:
            set_pending(
                PendingIntent(
                    intent=intent,
                    title=title,
                    date=None,
                    time=None,
                    content=None,
                    note_field="content",
                )
            )
            return AskResponse(
                model="notes",
                answer="**Missing Details**\n- **Content**\n\nWhat should the note say?",
                sources=[],
            )
        note_title = title or _derive_note_title(note_content)
        note = notes_service.create_note(
            notes_service.CreateNoteRequest(title=note_title, content=note_content)
        )
        return AskResponse(
            model="notes",
            answer=(
                "**Note Saved**\n"
                f"- **Title:** {note.title}\n"
                f"- **Content:** {note.content}"
            ),
            sources=[],
        )
    if intent == "update_note" or (intent == "chat" and _is_notes_update(message)):
        intent = "update_note"
        wants_rename = _wants_note_rename(message)
        extracted_query = _extract_note_title_candidate(message, intent) or _extract_notes_query(
            message
        )
        if wants_rename and extracted_query:
            note_query = extracted_query
        else:
            note_query = title or extracted_query
        new_title = _extract_note_new_title(message)
        note_content = content or _extract_note_content(message, intent)
        if wants_rename and not new_title and note_content:
            new_title, note_content = note_content, None
        if not note_query:
            note_field = "title" if wants_rename else "content"
            set_pending(
                PendingIntent(
                    intent=intent,
                    title=None,
                    date=None,
                    time=None,
                    content=note_content,
                    new_title=new_title,
                    note_field=note_field,
                )
            )
            return AskResponse(
                model="notes",
                answer="Which note should I update?",
                sources=[],
            )
        candidates_notes = notes_service.search_notes(note_query)
        candidates = _note_candidates_from_notes(candidates_notes)
        if not candidates:
            return AskResponse(
                model="notes",
                answer=f'I could not find any notes matching "{note_query}".',
                sources=[],
            )
        if len(candidates) > 1:
            set_pending(
                PendingIntent(
                    intent=intent,
                    title=note_query,
                    date=None,
                    time=None,
                    content=note_content,
                    new_title=new_title,
                    note_field="title" if wants_rename else "content",
                    selection=candidates,
                )
            )
            return AskResponse(
                model="notes",
                answer=_build_note_disambiguation_message(note_query, candidates),
                sources=[],
            )
        target = candidates[0]
        if not note_content and not new_title:
            note_field = "title" if wants_rename else "content"
            set_pending(
                PendingIntent(
                    intent=intent,
                    title=note_query,
                    date=None,
                    time=None,
                    content=None,
                    new_title=None,
                    note_field=note_field,
                    target=target,
                )
            )
            if note_field == "title":
                prompt = "**Missing Details**\n- **Title**\n\nWhat should the new title be?"
            else:
                prompt = "**Missing Details**\n- **Content**\n\nWhat should the note say?"
            return AskResponse(
                model="notes",
                answer=prompt,
                sources=[],
            )
        try:
            updated = notes_service.update_note(
                str(target.get("id")),
                notes_service.UpdateNoteRequest(title=new_title, content=note_content),
            )
        except ValueError as exc:
            return AskResponse(model="notes", answer=str(exc), sources=[])
        return AskResponse(
            model="notes",
            answer=(
                "**Note Updated**\n"
                f"- **Title:** {updated.title}\n"
                f"- **Content:** {updated.content}"
            ),
            sources=[],
        )
    if intent == "delete_note" or (intent == "chat" and _is_notes_delete(message)):
        intent = "delete_note"
        note_query = (
            title
            or _extract_note_title_candidate(message, intent)
            or _extract_notes_query(message)
        )
        if not note_query:
            set_pending(
                PendingIntent(
                    intent=intent,
                    title=None,
                    date=None,
                    time=None,
                    content=None,
                )
            )
            return AskResponse(
                model="notes",
                answer="Which note should I delete?",
                sources=[],
            )
        candidates_notes = notes_service.search_notes(note_query)
        candidates = _note_candidates_from_notes(candidates_notes)
        if not candidates:
            return AskResponse(
                model="notes",
                answer=f'I could not find any notes matching "{note_query}".',
                sources=[],
            )
        if len(candidates) > 1:
            set_pending(
                PendingIntent(
                    intent=intent,
                    title=note_query,
                    date=None,
                    time=None,
                    content=None,
                    selection=candidates,
                )
            )
            return AskResponse(
                model="notes",
                answer=_build_note_disambiguation_message(note_query, candidates),
                sources=[],
            )
        target = candidates[0]
        set_pending(
            PendingIntent(
                intent=intent,
                title=note_query,
                date=None,
                time=None,
                content=None,
                target=target,
                awaiting_confirmation=True,
            )
        )
        return AskResponse(
            model="notes",
            answer=_build_note_delete_confirmation(target),
            sources=[],
        )
    duration_minutes = extract_duration_minutes(message) if intent == "create_event" else None
    explicit_times = extract_explicit_times(message)
    range_start, range_end, range_ambiguous = extract_time_range(message)
    if range_ambiguous and intent in {"create_event", "update_event"}:
        return AskResponse(
            model="calendar",
            answer=_build_ambiguous_time_message(None),
            sources=[],
        )

    if intent == "create_event":
        if any(
            token in message.lower()
            for token in ["change", "move", "reschedule", "update", "shift", "push"]
        ):
            intent = "update_event"
            duration_minutes = None

    if intent in {"update_event", "delete_event", "create_event"}:
        if title is None or (
            isinstance(title, str)
            and any(
                token in title.lower()
                for token in ["change", "move", "reschedule", "update", "cancel", "delete"]
            )
        ):
            candidate = _extract_title_candidate(message, intent)
            if candidate:
                title = candidate

    if intent == "update_event" and len(explicit_times) >= 2:
        time_str = explicit_times[-1]
    if (
        intent == "create_event"
        and time_str
        and duration_minutes is None
        and len(explicit_times) >= 2
        and date_str
    ):
        inferred_duration = _duration_from_end_time(date_str, time_str, explicit_times[-1])
        if inferred_duration:
            duration_minutes = inferred_duration
        else:
            time_str = None
    if intent in {"create_event", "update_event"} and range_start and range_end:
        time_str = range_start
        if intent == "create_event" and duration_minutes is None:
            duration_minutes = _duration_between_times(range_start, range_end)

    if intent in {"create_event", "update_event"} and not explicit_times:
        parsed_time, time_ambiguous = extract_time(message)
        if time_ambiguous:
            set_pending(
                PendingIntent(
                    intent=intent,
                    title=title,
                    date=date_str,
                    time=None,
                    duration_minutes=duration_minutes,
                )
            )
            return AskResponse(
                model="calendar",
                answer=_build_ambiguous_time_message(parsed_time),
                sources=[],
            )

    if intent in {"create_event", "update_event", "delete_event"}:
        missing_title = title is None
        missing_date = date_str is None
        missing_time = time_str is None
        missing_duration = duration_minutes is None and intent == "create_event"
        if missing_time and intent in {"create_event", "update_event"}:
            parsed_time, time_ambiguous = extract_time(message)
            if time_ambiguous:
                set_pending(
                    PendingIntent(
                        intent=intent,
                        title=title,
                        date=date_str,
                        time=None,
                        duration_minutes=duration_minutes,
                    )
                )
                return AskResponse(
                    model="calendar",
                    answer=_build_ambiguous_time_message(parsed_time),
                    sources=[],
                )
        if intent in {"update_event", "delete_event"} and title and (
            missing_date or missing_time
        ):
            try:
                candidates = calendar_service.find_event_candidates(title, date_str)
            except CalendarActionError as exc:
                return AskResponse(model="calendar", answer=str(exc), sources=[])

            if len(candidates) > 1:
                set_pending(
                    PendingIntent(
                        intent=intent,
                        title=title,
                        date=date_str,
                        time=time_str,
                        selection=candidates,
                    )
                )
                return AskResponse(
                    model="calendar",
                    answer=calendar_service.build_disambiguation_message(
                        title, candidates
                    ),
                    sources=[],
                )
            if len(candidates) == 1 and intent == "delete_event":
                target = candidates[0]
                set_pending(
                    PendingIntent(
                        intent=intent,
                        title=title,
                        date=date_str,
                        time=time_str,
                        duration_minutes=duration_minutes,
                        target=target,
                        awaiting_confirmation=True,
                    )
                )
                return AskResponse(
                    model="calendar",
                    answer=build_delete_confirmation_message(target),
                    sources=[],
                )
        if missing_title or missing_date or missing_time or missing_duration:
            set_pending(
                PendingIntent(
                    intent=intent,
                    title=title,
                    date=date_str,
                    time=time_str,
                    duration_minutes=duration_minutes,
                )
            )
            return AskResponse(
                model="calendar",
                answer=_build_missing_details_message(
                    intent=intent,
                    title=title,
                    missing_title=missing_title,
                    missing_date=missing_date,
                    missing_time=missing_time,
                    missing_duration=missing_duration,
                ),
                sources=[],
            )

    if intent == "create_event":
        try:
            answer = calendar_service.create_event(
                title, date_str, time_str, duration_minutes
            )
        except CalendarConflictError as exc:
            set_pending(
                PendingIntent(
                    intent=intent,
                    title=title,
                    date=date_str,
                    time=time_str,
                    duration_minutes=duration_minutes,
                )
            )
            answer = str(exc)
        except CalendarActionError as exc:
            answer = str(exc)
        return AskResponse(model="calendar", answer=answer, sources=[])
    if intent == "query_calendar":
        clear_pending()
        try:
            answer = calendar_service.get_events(date_str, time_str)
        except CalendarActionError as exc:
            answer = str(exc)
        return AskResponse(model="calendar", answer=answer, sources=[])
    if intent == "update_event":
        try:
            answer = calendar_service.update_event(title, date_str, time_str)
        except CalendarConflictError as exc:
            set_pending(
                PendingIntent(
                    intent=intent,
                    title=title,
                    date=date_str,
                    time=time_str,
                )
            )
            answer = str(exc)
        except CalendarDisambiguationError as exc:
            set_pending(
                PendingIntent(
                    intent=intent,
                    title=title,
                    date=date_str,
                    time=time_str,
                    selection=exc.candidates,
                )
            )
            answer = str(exc)
        except CalendarActionError as exc:
            answer = str(exc)
        return AskResponse(model="calendar", answer=answer, sources=[])
    if intent == "delete_event":
        try:
            candidates = calendar_service.find_event_candidates(title, date_str)
            if len(candidates) == 1:
                target = candidates[0]
                set_pending(
                    PendingIntent(
                        intent=intent,
                        title=title,
                        date=date_str,
                        time=time_str,
                        duration_minutes=duration_minutes,
                        target=target,
                        awaiting_confirmation=True,
                    )
                )
                return AskResponse(
                    model="calendar",
                    answer=build_delete_confirmation_message(target),
                    sources=[],
                )
            answer = calendar_service.delete_event(title, date_str, time_str)
        except CalendarDisambiguationError as exc:
            set_pending(
                PendingIntent(
                    intent=intent,
                    title=title,
                    date=date_str,
                    time=time_str,
                    duration_minutes=duration_minutes,
                    selection=exc.candidates,
                )
            )
            answer = str(exc)
        except CalendarActionError as exc:
            answer = str(exc)
        return AskResponse(model="calendar", answer=answer, sources=[])
    if intent == "chat":
        clear_pending()
        try:
            llm = get_groq_chat_model()
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Groq configuration error: {str(exc)}",
            ) from exc

        prompt = CHAT_PROMPT_TEMPLATE.format(message=message.strip())
        try:
            result = await llm.ainvoke(prompt)
            content = result.content if hasattr(result, "content") else str(result)
            if isinstance(content, list):
                content = " ".join(str(item) for item in content)
            return AskResponse(model=llm.model_name, answer=str(content), sources=[])
        except Exception as exc:
            message_lower = str(exc).lower()
            status = 503 if any(token in message_lower for token in ["timeout", "temporar", "unavailable", "rate limit", "overloaded"]) else 502
            raise HTTPException(
                status_code=status,
                detail="Groq provider request failed. Check API key, model, and network connectivity.",
            ) from exc

    try:
        llm = get_groq_chat_model()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Groq configuration error: {str(exc)}",
        ) from exc

    try:
        results = search_index(query=message, k=payload.k)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to search embedding index: {str(exc)}",
        ) from exc

    if not results:
        raise HTTPException(
            status_code=404,
            detail="No relevant context found in embedding index.",
        )

    prompt = build_rag_prompt(question=message, sources=results)

    try:
        result = await llm.ainvoke(prompt)
        content = result.content if hasattr(result, "content") else str(result)
        if isinstance(content, list):
            content = " ".join(str(item) for item in content)
        return AskResponse(
            model=llm.model_name,
            answer=str(content),
            sources=[AskSource(**item) for item in results],
        )
    except Exception as exc:
        message = str(exc).lower()
        status = (
            503
            if any(
                token in message
                for token in [
                    "timeout",
                    "temporar",
                    "unavailable",
                    "rate limit",
                    "overloaded",
                ]
            )
            else 502
        )
        raise HTTPException(
            status_code=status,
            detail="Groq provider request failed. Check API key, model, and network connectivity.",
        ) from exc
