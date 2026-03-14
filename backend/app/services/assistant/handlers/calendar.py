from __future__ import annotations

from datetime import datetime, timedelta

from app.services import calendar_service
from app.services.calendar_service import (
    CalendarActionError,
    CalendarConflictError,
    CalendarDisambiguationError,
    build_delete_confirmation_message,
)
from app.services.conversation_state import PendingIntent, clear_pending, set_pending
from app.services.temporal_parser import (
    extract_date,
    extract_duration_minutes,
    extract_explicit_times,
    extract_time,
    extract_time_range,
    strip_temporal_tokens,
)
from app.services.assistant.schemas import AskResponse
from app.services.assistant.utils import (
    _extract_selection_by_id,
    _extract_selection_index,
    _parse_confirmation,
)


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


def handle_pending(message: str, pending: PendingIntent) -> AskResponse | None:
    if pending.intent not in {"create_event", "update_event", "delete_event"}:
        return None

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

    return None


def handle_intent(
    message: str, intent: str, intent_data: dict[str, object]
) -> AskResponse | None:
    title = intent_data.get("title") if isinstance(intent_data, dict) else None
    date_str = intent_data.get("date") if isinstance(intent_data, dict) else None
    time_str = intent_data.get("time") if isinstance(intent_data, dict) else None

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

    return None
