from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import HTTPException

from app.services import calendar_service, notes_service
from app.services.assistant.extraction import extract_notes_and_events
from app.services.assistant.schemas import AskResponse
from app.services.assistant.utils import _parse_confirmation
from app.services.conversation_state import PendingIntent, clear_pending, set_pending
from app.services.temporal_parser import (
    extract_date,
    extract_duration_minutes,
    extract_time,
    extract_time_range,
)


def _preview(text: str, limit: int = 200) -> str:
    cleaned = " ".join((text or "").split())
    if len(cleaned) > limit:
        return f"{cleaned[:limit-3]}..."
    return cleaned


def _format_note_prompt(note: dict[str, Any], index: int, total: int) -> str:
    title = note.get("title") or "Untitled"
    content = note.get("content") or ""
    snippet = note.get("source_snippet")
    lines = [
        f"**Note Draft {index} of {total}**",
        f"- **Title:** {title}",
        f"- **Preview:** { _preview(content, 240) }",
    ]
    if snippet:
        lines.append(f"- **Source:** { _preview(str(snippet), 180) }")
    lines.append(
        "Save this note? Reply `yes` or `no`. You can also say `edit title ...` or `edit content ...`."
    )
    return "\n".join(lines)


def _parse_note_edit(message: str) -> tuple[str | None, str | None]:
    lowered = message.strip().lower()
    if not lowered:
        return None, None
    if lowered.startswith("edit title"):
        return "title", message.split(" ", 2)[-1].strip()
    if lowered.startswith("edit content"):
        return "content", message.split(" ", 2)[-1].strip()
    if "title:" in lowered:
        parts = message.split(":", 1)
        if len(parts) == 2 and "title" in parts[0].lower():
            return "title", parts[1].strip()
    if "content:" in lowered:
        parts = message.split(":", 1)
        if len(parts) == 2 and "content" in parts[0].lower():
            return "content", parts[1].strip()
    return None, None


def _next_missing_event_index(events: list[dict[str, Any]]) -> int | None:
    for idx, event in enumerate(events):
        if not event.get("time") or not event.get("duration_minutes"):
            return idx
    return None


def _format_event_detail_prompt(event: dict[str, Any]) -> str:
    title = event.get("title") or "Untitled"
    date_str = event.get("date") or "unknown date"
    snippet = event.get("source_snippet")
    description = event.get("description")
    lines = [
        "**Event Details Needed**",
        f"- **Title:** {title}",
        f"- **Date:** {date_str}",
    ]
    if description:
        lines.append(f"- **Description:** { _preview(str(description), 160) }")
    if snippet:
        lines.append(f"- **Source:** { _preview(str(snippet), 180) }")
    lines.append(
        "What time and duration should I use? (e.g., `3pm for 60 minutes`)\n"
        "You can also say `edit title ...`, `edit date ...`, or `add description ...`."
    )
    return "\n".join(lines)


def _format_event_confirmation(events: list[dict[str, Any]]) -> str:
    lines = ["**Confirm Events**", "Reply `yes` to create all or `no` to cancel."]
    for idx, event in enumerate(events, start=1):
        title = event.get("title") or "Untitled"
        date_str = event.get("date") or "unknown date"
        time_str = event.get("time") or "time needed"
        duration = event.get("duration_minutes")
        duration_str = f"{duration} min" if duration else "duration needed"
        description = event.get("description")
        line = f"{idx}) **{title}** — {date_str} at {time_str} ({duration_str})"
        if description:
            line += f" — { _preview(str(description), 80) }"
        lines.append(line)
    return "\n".join(lines)


def _parse_event_edits(message: str) -> dict[str, str | None]:
    import re

    edits: dict[str, str | None] = {}
    if not message or not message.strip():
        return edits

    title_match = re.search(r"\bedit\s+title\s+(?:to\s+)?(.+)$", message, re.IGNORECASE)
    if not title_match:
        title_match = re.search(r"\btitle\s*:\s*(.+)$", message, re.IGNORECASE)
    if title_match:
        edits["title"] = title_match.group(1).strip()

    date_match = re.search(r"\bedit\s+date\s+(?:to\s+)?(.+)$", message, re.IGNORECASE)
    if not date_match:
        date_match = re.search(r"\bdate\s*:\s*(.+)$", message, re.IGNORECASE)
    if date_match:
        edits["date_raw"] = date_match.group(1).strip()

    desc_match = re.search(r"\b(?:add\s+)?description\s*[:\-]?\s*(.+)$", message, re.IGNORECASE)
    if not desc_match:
        desc_match = re.search(r"\bdesc(?:ription)?\s*:\s*(.+)$", message, re.IGNORECASE)
    if not desc_match:
        desc_match = re.search(r"\bnotes?\s*:\s*(.+)$", message, re.IGNORECASE)
    if desc_match:
        edits["description"] = desc_match.group(1).strip()

    return edits


async def handle_extraction(
    instruction: str,
    document_text: str,
) -> AskResponse:
    try:
        result = await extract_notes_and_events(instruction, document_text)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Extraction request failed: {str(exc)}",
        ) from exc

    notes = result.get("notes", [])
    events = result.get("events", [])
    if not notes and not events:
        clear_pending()
        return AskResponse(
            model="assistant",
            answer="I couldn't extract any notes or events from the document.",
            sources=[],
        )

    pending = PendingIntent(
        intent="extraction",
        title=None,
        date=None,
        time=None,
        content=None,
        bulk_notes=notes or None,
        note_index=0 if notes else None,
        awaiting_note_confirmation=bool(notes),
        saved_notes=[],
        skipped_notes=[],
        bulk_events=events or None,
        event_index=None,
        awaiting_event_details=False,
        awaiting_bulk_event_confirmation=False,
    )

    if notes:
        set_pending(pending)
        return AskResponse(
            model="assistant",
            answer=_format_note_prompt(notes[0], 1, len(notes)),
            sources=[],
        )

    if events:
        next_idx = _next_missing_event_index(events)
        pending.event_index = next_idx
        if next_idx is not None:
            pending.awaiting_event_details = True
            set_pending(pending)
            return AskResponse(
                model="assistant",
                answer=_format_event_detail_prompt(events[next_idx]),
                sources=[],
            )
        pending.awaiting_bulk_event_confirmation = True
        set_pending(pending)
        return AskResponse(
            model="assistant",
            answer=_format_event_confirmation(events),
            sources=[],
        )

    clear_pending()
    return AskResponse(
        model="assistant",
        answer="I couldn't extract any notes or events from the document.",
        sources=[],
    )


def handle_pending(message: str, pending: PendingIntent) -> AskResponse | None:
    if not (
        pending.bulk_notes
        or pending.bulk_events
        or pending.awaiting_note_confirmation
        or pending.awaiting_event_details
        or pending.awaiting_bulk_event_confirmation
    ):
        return None

    # Note confirmation loop
    if pending.awaiting_note_confirmation and pending.bulk_notes:
        index = pending.note_index or 0
        if index >= len(pending.bulk_notes):
            pending.awaiting_note_confirmation = False
        else:
            note = pending.bulk_notes[index]
            field, value = _parse_note_edit(message)
            if field and value:
                note[field] = value.strip()
                pending.bulk_notes[index] = note
                set_pending(pending)
                return AskResponse(
                    model="assistant",
                    answer=_format_note_prompt(note, index + 1, len(pending.bulk_notes)),
                    sources=[],
                )
            decision = _parse_confirmation(message)
            if decision is None:
                return AskResponse(
                    model="assistant",
                    answer=_format_note_prompt(note, index + 1, len(pending.bulk_notes)),
                    sources=[],
                )
            if decision:
                try:
                    created = notes_service.create_note(
                        notes_service.CreateNoteRequest(
                            title=str(note.get("title") or "Untitled")[:120],
                            content=str(note.get("content") or "")[:5000],
                        )
                    )
                    if pending.saved_notes is None:
                        pending.saved_notes = []
                    pending.saved_notes.append(created.title)
                except Exception as exc:
                    return AskResponse(
                        model="assistant",
                        answer=f"Failed to save note: {str(exc)}",
                        sources=[],
                    )
            else:
                if pending.skipped_notes is None:
                    pending.skipped_notes = []
                pending.skipped_notes.append(str(note.get("title") or "Untitled"))

            pending.note_index = index + 1
            if pending.note_index < len(pending.bulk_notes):
                set_pending(pending)
                next_note = pending.bulk_notes[pending.note_index]
                return AskResponse(
                    model="assistant",
                    answer=_format_note_prompt(
                        next_note, pending.note_index + 1, len(pending.bulk_notes)
                    ),
                    sources=[],
                )

            pending.awaiting_note_confirmation = False

    # After notes, move to events if present
    if not pending.awaiting_note_confirmation and pending.bulk_events:
        if pending.awaiting_event_details:
            idx = pending.event_index if pending.event_index is not None else 0
            if idx >= len(pending.bulk_events):
                pending.awaiting_event_details = False
            else:
                event = pending.bulk_events[idx]
                edits = _parse_event_edits(message)
                if "title" in edits and edits["title"]:
                    event["title"] = edits["title"]
                if "description" in edits:
                    event["description"] = edits["description"]
                if "date_raw" in edits and edits["date_raw"]:
                    parsed_edit_date = extract_date(edits["date_raw"])
                    if parsed_edit_date:
                        event["date"] = parsed_edit_date

                parsed_date = event.get("date")
                range_start, range_end, range_ambiguous = extract_time_range(message)
                parsed_time, time_ambiguous = extract_time(message)
                if range_ambiguous or time_ambiguous:
                    return AskResponse(
                        model="assistant",
                        answer="**Clarification Needed**\n- Please specify a time with AM/PM, like `4pm`.",
                        sources=[],
                    )
                duration = extract_duration_minutes(message)
                if range_start and range_end:
                    parsed_time = range_start
                    if duration is None:
                        start_dt = datetime.strptime(range_start, "%H:%M")
                        end_dt = datetime.strptime(range_end, "%H:%M")
                        delta_minutes = int((end_dt - start_dt).total_seconds() // 60)
                        if delta_minutes <= 0:
                            delta_minutes += 24 * 60
                        delta = delta_minutes
                        duration = delta if delta > 0 else None

                missing = []
                if not parsed_date:
                    missing.append("**Date**")
                if not parsed_time:
                    missing.append("**Time**")
                if not duration:
                    missing.append("**Duration**")
                if missing:
                    return AskResponse(
                        model="assistant",
                        answer="**Missing Details**\n- "
                        + "\n- ".join(missing)
                        + "\n\nPlease provide the missing details.",
                        sources=[],
                    )

                event["date"] = parsed_date
                event["time"] = parsed_time
                event["duration_minutes"] = duration
                pending.bulk_events[idx] = event

                next_missing = _next_missing_event_index(pending.bulk_events)
                if next_missing is not None:
                    pending.event_index = next_missing
                    set_pending(pending)
                    return AskResponse(
                        model="assistant",
                        answer=_format_event_detail_prompt(pending.bulk_events[next_missing]),
                        sources=[],
                    )

                pending.awaiting_event_details = False
                pending.awaiting_bulk_event_confirmation = True
                set_pending(pending)
                return AskResponse(
                    model="assistant",
                    answer=_format_event_confirmation(pending.bulk_events),
                    sources=[],
                )

        if pending.awaiting_bulk_event_confirmation:
            decision = _parse_confirmation(message)
            if decision is None:
                return AskResponse(
                    model="assistant",
                    answer=_format_event_confirmation(pending.bulk_events),
                    sources=[],
                )
            if not decision:
                clear_pending()
                return AskResponse(
                    model="assistant",
                    answer="Okay, I won't create those events.",
                    sources=[],
                )

            created_titles: list[str] = []
            for event in pending.bulk_events:
                try:
                    answer = calendar_service.create_event(
                        event.get("title"),
                        event.get("date"),
                        event.get("time"),
                        event.get("duration_minutes"),
                        event.get("description"),
                    )
                    _ = answer
                    created_titles.append(str(event.get("title") or "Untitled"))
                except Exception as exc:
                    clear_pending()
                    return AskResponse(
                        model="assistant",
                        answer=(
                            "Some events may have been created before an error occurred.\n"
                            f"Error: {str(exc)}"
                        ),
                        sources=[],
                    )

            clear_pending()
            summary = "\n".join(f"- {title}" for title in created_titles) or "None"
            return AskResponse(
                model="assistant",
                answer="**Events Created**\n" + summary,
                sources=[],
            )

        next_missing = _next_missing_event_index(pending.bulk_events)
        if next_missing is not None:
            pending.event_index = next_missing
            pending.awaiting_event_details = True
            set_pending(pending)
            return AskResponse(
                model="assistant",
                answer=_format_event_detail_prompt(pending.bulk_events[next_missing]),
                sources=[],
            )
        pending.awaiting_bulk_event_confirmation = True
        set_pending(pending)
        return AskResponse(
            model="assistant",
            answer=_format_event_confirmation(pending.bulk_events),
            sources=[],
        )

    # If notes finished and no events, summarize
    if not pending.awaiting_note_confirmation and not pending.bulk_events:
        saved = pending.saved_notes or []
        skipped = pending.skipped_notes or []
        clear_pending()
        return AskResponse(
            model="assistant",
            answer=(
                "**Notes Complete**\n"
                f"- Saved: {len(saved)}\n"
                f"- Skipped: {len(skipped)}"
            ),
            sources=[],
        )

    set_pending(pending)
    return None
