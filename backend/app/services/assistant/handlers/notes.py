from __future__ import annotations

from datetime import datetime

from app.services import notes_service
from app.services.conversation_state import PendingIntent, clear_pending, set_pending
from app.services.assistant.schemas import AskResponse
from app.services.assistant.utils import (
    _extract_selection_by_id,
    _extract_selection_index,
    _parse_confirmation,
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


def handle_pending(message: str, pending: PendingIntent) -> AskResponse | None:
    if pending.intent not in {"create_note", "update_note", "delete_note"}:
        return None

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

    return None


def handle_intent(message: str, intent: str, intent_data: dict[str, object]) -> AskResponse | None:
    title = intent_data.get("title") if isinstance(intent_data, dict) else None
    content = intent_data.get("content") if isinstance(intent_data, dict) else None

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

    return None
