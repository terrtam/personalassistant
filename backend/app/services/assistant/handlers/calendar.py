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
    extract_weekdays,
    strip_temporal_tokens,
)
from app.services.assistant.schemas import AskResponse
from app.services.assistant.utils import (
    _extract_selection_by_id,
    _extract_selection_index,
    _parse_confirmation,
)


def _local_tz():
    return datetime.now().astimezone().tzinfo


def _format_datetime_label(dt: datetime | None) -> str | None:
    if not dt:
        return None
    return dt.strftime("%a %b %d, %Y at %H:%M %Z").strip()


def _format_weekday_label(code: str) -> str:
    mapping = {
        "MO": "Monday",
        "TU": "Tuesday",
        "WE": "Wednesday",
        "TH": "Thursday",
        "FR": "Friday",
        "SA": "Saturday",
        "SU": "Sunday",
    }
    return mapping.get(code.upper(), code)


def _build_missing_details_message(
    intent: str,
    title: str | None,
    missing_title: bool,
    missing_date: bool,
    missing_time: bool,
    missing_duration: bool,
    date_str: str | None = None,
    time_str: str | None = None,
    duration_minutes: int | None = None,
    recurrence: dict | None = None,
) -> str:
    event_label = f'"{title}"' if title else "the event"
    missing_parts: list[str] = []
    if missing_title:
        missing_parts.append("**Title**")
    if missing_date:
        missing_parts.append("**Start Date**" if recurrence else "**Date**")
    if missing_time:
        missing_parts.append("**Time**")
    if missing_duration:
        missing_parts.append("**End Time / Duration**")
    header = "**Missing Details**"
    draft_lines: list[str] = []
    if title:
        draft_lines.append(f"- **Title:** {title}")
    if date_str and time_str:
        try:
            start_dt = datetime.combine(
                datetime.fromisoformat(date_str).date(),
                datetime.strptime(time_str, "%H:%M").time(),
                tzinfo=_local_tz(),
            )
        except ValueError:
            start_dt = None
        start_label = _format_datetime_label(start_dt)
        if start_label:
            draft_lines.append(f"- **Starts:** _{start_label}_")
        if duration_minutes:
            end_dt = start_dt + timedelta(minutes=duration_minutes) if start_dt else None
            end_label = _format_datetime_label(end_dt)
            if end_label:
                draft_lines.append(f"- **Ends:** _{end_label}_")
    if recurrence:
        recurrence_summary = _format_recurrence_summary(recurrence)
        if recurrence_summary:
            draft_lines.append(f"- **Repeats:** {recurrence_summary}")
    bullets = "\n".join(f"- {part}" for part in missing_parts) if missing_parts else ""
    question = "Could you share the remaining event details?"
    if intent == "create_event":
        if missing_title and missing_date and missing_time:
            if recurrence:
                question = "What should I call the event, and what start date/time should I use for the series?"
            else:
                question = "What should I call the event, and what date/time should I schedule it?"
        if missing_duration and not (missing_title or missing_date or missing_time):
            question = "When should it end? (You can also say a duration like 45 minutes.)"
        if missing_title and missing_date:
            if recurrence:
                question = "What should I call the event, and what start date should I use for the series?"
            else:
                question = "What should I call the event, and what date should I schedule it?"
        if missing_title and missing_time:
            question = "What should I call the event, and what time should I schedule it?"
        if missing_title:
            question = "What should I call the event?"
        if missing_date and missing_time:
            if recurrence:
                question = f"What start date and time should I use for {event_label}?"
            else:
                question = f"What date and time should I schedule {event_label}?"
        if missing_date:
            if recurrence:
                question = f"What start date should I use for {event_label}?"
            else:
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
    draft_block = ""
    if draft_lines:
        draft_block = "**Current Draft**\n" + "\n".join(draft_lines) + "\n\n"
    if bullets:
        return f"{draft_block}{header}\n{bullets}\n\n{question}"
    return f"{draft_block}{header}\n\n{question}"


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


def _parse_apply_to(message: str) -> str | None:
    if not message:
        return None
    lowered = message.lower()
    if any(
        phrase in lowered
        for phrase in [
            "this occurrence",
            "just this",
            "only this",
            "this one",
            "single occurrence",
            "this instance",
        ]
    ):
        return "single"
    if any(
        phrase in lowered
        for phrase in [
            "entire series",
            "the series",
            "all occurrences",
            "every occurrence",
            "whole series",
        ]
    ):
        return "series"
    return None


def _is_recurring_request(message: str) -> bool:
    if not message:
        return False
    lowered = message.lower()
    return any(
        token in lowered
        for token in [
            "every ",
            "weekly",
            "recurring",
            "repeat",
            "daily",
            "monthly",
            "yearly",
        ]
    )


def _build_recurrence_from_message(message: str, date_str: str | None) -> dict | None:
    if not _is_recurring_request(message):
        return None
    lowered = message.lower()
    frequency = None
    interval = 1

    if "daily" in lowered:
        frequency = "daily"
    if "weekly" in lowered:
        frequency = "weekly"
    if "monthly" in lowered:
        frequency = "monthly"
    if "yearly" in lowered or "annually" in lowered:
        frequency = "yearly"

    if frequency is None and "every" in lowered:
        import re

        match = re.search(r"\bevery\s+(\d+)\s+(day|week|month|year)s?\b", lowered)
        if match:
            interval = int(match.group(1))
            unit = match.group(2)
            if unit == "day":
                frequency = "daily"
            elif unit == "week":
                frequency = "weekly"
            elif unit == "month":
                frequency = "monthly"
            elif unit == "year":
                frequency = "yearly"

    if frequency is None:
        frequency = "weekly"

    byweekday = None
    if frequency == "weekly":
        byweekday = extract_weekdays(message)
        if not byweekday and date_str:
            try:
                weekday_idx = datetime.fromisoformat(date_str).weekday()
                weekday_codes = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
                byweekday = [weekday_codes[weekday_idx]]
            except ValueError:
                byweekday = None

    return {
        "frequency": frequency,
        "interval": interval,
        "byweekday": byweekday,
        "ends": {"type": "never", "date": None, "count": None},
    }


def _apply_recurrence_ends_from_message(
    message: str, recurrence: dict | None
) -> dict | None:
    if not recurrence or not message:
        return recurrence
    lowered = message.lower()
    if "never" in lowered:
        recurrence["ends"] = {"type": "never", "date": None, "count": None}
        return recurrence

    import re

    after_match = re.search(
        r"\bafter\s+(\d+)\s+(occurrence|occurrences|times)\b", lowered
    )
    if after_match:
        count = int(after_match.group(1))
        if count > 0:
            recurrence["ends"] = {"type": "after", "date": None, "count": count}
            return recurrence

    if "until" in lowered or "on" in lowered or "ends" in lowered:
        extracted_date = extract_date(message)
        if extracted_date:
            recurrence["ends"] = {"type": "on", "date": extracted_date, "count": None}
            return recurrence

    return recurrence


def _format_recurrence_summary(recurrence: dict | None) -> str | None:
    if not recurrence:
        return None
    frequency = recurrence.get("frequency")
    interval = recurrence.get("interval") or 1
    byweekday = recurrence.get("byweekday") or []
    ends = recurrence.get("ends") or {}
    parts: list[str] = []
    if frequency:
        label = frequency
        if interval and interval > 1:
            label = f"every {interval} {frequency.rstrip('ly')}s"
        elif frequency == "weekly":
            label = "every week"
        elif frequency == "daily":
            label = "every day"
        elif frequency == "monthly":
            label = "every month"
        elif frequency == "yearly":
            label = "every year"
        parts.append(label)
    if byweekday:
        readable = [_format_weekday_label(code) for code in byweekday]
        parts.append(f"on {', '.join(readable)}")
    if isinstance(ends, dict):
        if ends.get("type") == "on" and ends.get("date"):
            parts.append(f"until {ends['date']}")
        if ends.get("type") == "after" and ends.get("count"):
            parts.append(f"for {ends['count']} occurrences")
    return " ".join(parts) if parts else None


def _extract_title_edit(message: str) -> str | None:
    if not message:
        return None
    import re

    patterns = [
        re.compile(r"\b(?:title|name)\s*(?:is|to|:)\s*(.+)$", re.IGNORECASE),
        re.compile(r"\brename\s+(?:it\s+)?to\s+(.+)$", re.IGNORECASE),
    ]
    for pattern in patterns:
        match = pattern.search(message)
        if match:
            value = match.group(1).strip(" .")
            return value or None
    return None


def _build_create_update_confirmation_message(
    intent: str,
    title: str,
    date_str: str,
    time_str: str,
    duration_minutes: int | None,
    recurrence: dict | None,
) -> str:
    try:
        start_dt = datetime.combine(
            datetime.fromisoformat(date_str).date(),
            datetime.strptime(time_str, "%H:%M").time(),
            tzinfo=_local_tz(),
        )
    except ValueError:
        start_dt = None
    end_line = ""
    if duration_minutes and start_dt:
        end_dt = start_dt + timedelta(minutes=duration_minutes)
        end_label = _format_datetime_label(end_dt)
        end_line = f"- **Ends:** _{end_label}_\n" if end_label else ""
    elif intent == "update_event" and duration_minutes is None:
        end_line = "- **Ends:** (unchanged)\n"
    recurrence_line = ""
    recurrence_summary = _format_recurrence_summary(recurrence)
    if recurrence_summary:
        recurrence_line = f"- **Repeats:** {recurrence_summary}\n"
    action = "Create" if intent == "create_event" else "Update"
    start_label = _format_datetime_label(start_dt) if start_dt else None
    return (
        f"**Confirm {action}**\n"
        f"- **Title:** {title}\n"
        f"- **Starts:** _{start_label or 'time unknown'}_\n"
        f"{end_line}"
        f"{recurrence_line}\n"
        "Reply `yes` to confirm or `no` to cancel."
    )


def _build_series_choice_message(intent: str) -> str:
    if intent == "delete_event":
        return (
            "**Clarification Needed**\n"
            "- Do you want to cancel **this occurrence** or the **entire series**?"
        )
    return (
        "**Clarification Needed**\n"
        "- Do you want to update **this occurrence** or the **entire series**?"
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

    if pending.awaiting_series_choice:
        choice = _parse_apply_to(message)
        if not choice:
            return AskResponse(
                model="calendar",
                answer=_build_series_choice_message(pending.intent),
                sources=[],
            )
        if pending.intent == "delete_event":
            set_pending(
                PendingIntent(
                    intent=pending.intent,
                    title=pending.title,
                    date=pending.date,
                    time=pending.time,
                    duration_minutes=pending.duration_minutes,
                    recurrence=pending.recurrence,
                    apply_to=choice,
                    target=pending.target,
                    awaiting_confirmation=True,
                )
            )
            return AskResponse(
                model="calendar",
                answer=build_delete_confirmation_message(
                    pending.target, scope=choice
                ),
                sources=[],
            )
        set_pending(
            PendingIntent(
                intent=pending.intent,
                title=pending.title,
                date=pending.date,
                time=pending.time,
                duration_minutes=pending.duration_minutes,
                recurrence=pending.recurrence,
                apply_to=choice,
                target=pending.target,
                awaiting_confirmation=bool(pending.date and pending.time),
            )
        )
        if pending.date and pending.time:
            return AskResponse(
                model="calendar",
                answer=_build_create_update_confirmation_message(
                    pending.intent,
                    pending.title or "Untitled event",
                    pending.date,
                    pending.time,
                    pending.duration_minutes,
                    pending.recurrence,
                ),
                sources=[],
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

    if pending.awaiting_confirmation and pending.intent in {"create_event", "update_event"}:
        decision = _parse_confirmation(message)
        if decision is None:
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

            title_edit = _extract_title_edit(message)

            merged_date = parsed_date or pending.date
            merged_time = parsed_time or pending.time
            merged_title = title_edit or pending.title
            merged_duration = parsed_duration or pending.duration_minutes
            merged_apply_to = _parse_apply_to(message) or pending.apply_to

            merged_recurrence = pending.recurrence
            if _is_recurring_request(message):
                merged_recurrence = _build_recurrence_from_message(
                    message, merged_date
                )
            if merged_recurrence:
                merged_recurrence = _apply_recurrence_ends_from_message(
                    message, merged_recurrence
                )
            elif pending.recurrence:
                merged_recurrence = _apply_recurrence_ends_from_message(
                    message, dict(pending.recurrence)
                )

            set_pending(
                PendingIntent(
                    intent=pending.intent,
                    title=merged_title,
                    date=merged_date,
                    time=merged_time,
                    duration_minutes=merged_duration,
                    recurrence=merged_recurrence,
                    apply_to=merged_apply_to,
                    target=pending.target,
                    awaiting_confirmation=True,
                )
            )

            if (
                pending.intent == "create_event"
                and (merged_title is None or merged_date is None or merged_time is None or merged_duration is None)
            ):
                return AskResponse(
                    model="calendar",
                    answer=_build_missing_details_message(
                        intent=pending.intent,
                        title=merged_title,
                        missing_title=merged_title is None,
                        missing_date=merged_date is None,
                        missing_time=merged_time is None,
                        missing_duration=merged_duration is None,
                        date_str=merged_date,
                        time_str=merged_time,
                        duration_minutes=merged_duration,
                        recurrence=merged_recurrence,
                    ),
                    sources=[],
                )

            return AskResponse(
                model="calendar",
                answer=_build_create_update_confirmation_message(
                    pending.intent,
                    merged_title or "Untitled event",
                    merged_date,
                    merged_time,
                    merged_duration,
                    merged_recurrence,
                ),
                sources=[],
            )

        if decision:
            clear_pending()
            try:
                if pending.intent == "create_event":
                    answer = calendar_service.create_event(
                        pending.title,
                        pending.date,
                        pending.time,
                        pending.duration_minutes,
                        recurrence=pending.recurrence,
                    )
                else:
                    if pending.target:
                        answer = calendar_service.update_event_from_candidate(
                            pending.target,
                            pending.date,
                            pending.time,
                            recurrence=pending.recurrence,
                            apply_to=pending.apply_to,
                        )
                    else:
                        answer = calendar_service.update_event(
                            pending.title,
                            pending.date,
                            pending.time,
                            recurrence=pending.recurrence,
                            apply_to=pending.apply_to,
                        )
            except CalendarConflictError as exc:
                set_pending(
                    PendingIntent(
                        intent=pending.intent,
                        title=pending.title,
                        date=pending.date,
                        time=pending.time,
                        duration_minutes=pending.duration_minutes,
                        recurrence=pending.recurrence,
                        apply_to=pending.apply_to,
                        target=pending.target,
                    )
                )
                return AskResponse(model="calendar", answer=str(exc), sources=[])
            except CalendarActionError as exc:
                message_text = str(exc)
                if (
                    pending.intent == "update_event"
                    and "occurrence" in message_text.lower()
                    and "series" in message_text.lower()
                ):
                    set_pending(
                        PendingIntent(
                            intent=pending.intent,
                            title=pending.title,
                            date=pending.date,
                            time=pending.time,
                            duration_minutes=pending.duration_minutes,
                            recurrence=pending.recurrence,
                            target=pending.target,
                            awaiting_series_choice=True,
                        )
                    )
                    return AskResponse(
                        model="calendar",
                        answer=_build_series_choice_message(pending.intent),
                        sources=[],
                    )
                answer = message_text
            return AskResponse(model="calendar", answer=answer, sources=[])
        clear_pending()
        return AskResponse(
            model="calendar",
            answer="Okay, I won't make that change.",
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
                answer = calendar_service.delete_event_from_candidate(
                    pending.target, apply_to=pending.apply_to
                )
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
        merged_apply_to = _parse_apply_to(message) or pending.apply_to
        if pending.intent == "update_event":
            if merged_date and merged_time:
                if pending.target.get("recurringEventId") and merged_apply_to is None:
                    set_pending(
                        PendingIntent(
                            intent=pending.intent,
                            title=pending.title,
                            date=merged_date,
                            time=merged_time,
                            duration_minutes=pending.duration_minutes,
                            recurrence=pending.recurrence,
                            target=pending.target,
                            awaiting_series_choice=True,
                        )
                    )
                    return AskResponse(
                        model="calendar",
                        answer=_build_series_choice_message(pending.intent),
                        sources=[],
                    )
                set_pending(
                    PendingIntent(
                        intent=pending.intent,
                        title=pending.title,
                        date=merged_date,
                        time=merged_time,
                        duration_minutes=pending.duration_minutes,
                        recurrence=pending.recurrence,
                        apply_to=merged_apply_to,
                        target=pending.target,
                        awaiting_confirmation=True,
                    )
                )
                return AskResponse(
                    model="calendar",
                    answer=_build_create_update_confirmation_message(
                        pending.intent,
                        pending.title or "Untitled event",
                        merged_date,
                        merged_time,
                        pending.duration_minutes,
                        pending.recurrence,
                    ),
                    sources=[],
                )

            set_pending(
                PendingIntent(
                    intent=pending.intent,
                    title=pending.title,
                    date=merged_date,
                    time=merged_time,
                    duration_minutes=pending.duration_minutes,
                    recurrence=pending.recurrence,
                    apply_to=merged_apply_to,
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
                    date_str=merged_date,
                    time_str=merged_time,
                    duration_minutes=pending.duration_minutes,
                    recurrence=pending.recurrence,
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
                            recurrence=pending.recurrence,
                            apply_to=pending.apply_to,
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
                            date_str=pending.date,
                            time_str=pending.time,
                            duration_minutes=pending.duration_minutes,
                            recurrence=pending.recurrence,
                        ),
                        sources=[],
                    )
                if selected.get("recurringEventId") and pending.apply_to is None:
                    set_pending(
                        PendingIntent(
                            intent=pending.intent,
                            title=pending.title,
                            date=pending.date,
                            time=pending.time,
                            duration_minutes=pending.duration_minutes,
                            recurrence=pending.recurrence,
                            target=selected,
                            awaiting_series_choice=True,
                        )
                    )
                    return AskResponse(
                        model="calendar",
                        answer=_build_series_choice_message(pending.intent),
                        sources=[],
                    )
                set_pending(
                    PendingIntent(
                        intent=pending.intent,
                        title=pending.title,
                        date=pending.date,
                        time=pending.time,
                        duration_minutes=pending.duration_minutes,
                        recurrence=pending.recurrence,
                        apply_to=pending.apply_to,
                        target=selected,
                        awaiting_confirmation=True,
                    )
                )
                return AskResponse(
                    model="calendar",
                    answer=_build_create_update_confirmation_message(
                        pending.intent,
                        pending.title or "Untitled event",
                        pending.date,
                        pending.time,
                        pending.duration_minutes,
                        pending.recurrence,
                    ),
                    sources=[],
                )
            if pending.intent == "delete_event":
                if selected.get("recurringEventId") and pending.apply_to is None:
                    set_pending(
                        PendingIntent(
                            intent=pending.intent,
                            title=pending.title,
                            date=pending.date,
                            time=pending.time,
                            duration_minutes=pending.duration_minutes,
                            recurrence=pending.recurrence,
                            target=selected,
                            awaiting_series_choice=True,
                        )
                    )
                    return AskResponse(
                        model="calendar",
                        answer=_build_series_choice_message(pending.intent),
                        sources=[],
                    )
                set_pending(
                    PendingIntent(
                        intent=pending.intent,
                        title=pending.title,
                        date=pending.date,
                        time=pending.time,
                        duration_minutes=pending.duration_minutes,
                        apply_to=pending.apply_to,
                        target=selected,
                        awaiting_confirmation=True,
                    )
                )
                return AskResponse(
                    model="calendar",
                    answer=build_delete_confirmation_message(
                        selected, scope=pending.apply_to
                    ),
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
    merged_apply_to = _parse_apply_to(message) or pending.apply_to
    merged_recurrence = pending.recurrence
    if merged_recurrence is None:
        merged_recurrence = _build_recurrence_from_message(message, merged_date)

    if merged_title or merged_date or merged_time or merged_duration is not None:
        if merged_title and merged_date and merged_time and (
            pending.intent != "create_event" or merged_duration is not None
        ):
            intent = pending.intent
            if intent == "create_event":
                set_pending(
                    PendingIntent(
                        intent=intent,
                        title=merged_title,
                        date=merged_date,
                        time=merged_time,
                        duration_minutes=merged_duration,
                        recurrence=merged_recurrence,
                        awaiting_confirmation=True,
                    )
                )
                return AskResponse(
                    model="calendar",
                    answer=_build_create_update_confirmation_message(
                        intent,
                        merged_title,
                        merged_date,
                        merged_time,
                        merged_duration,
                        merged_recurrence,
                    ),
                    sources=[],
                )
            if intent == "update_event":
                set_pending(
                    PendingIntent(
                        intent=intent,
                        title=merged_title,
                        date=merged_date,
                        time=merged_time,
                        duration_minutes=merged_duration,
                        recurrence=merged_recurrence,
                        apply_to=merged_apply_to,
                        awaiting_confirmation=True,
                    )
                )
                return AskResponse(
                    model="calendar",
                    answer=_build_create_update_confirmation_message(
                        intent,
                        merged_title,
                        merged_date,
                        merged_time,
                        merged_duration,
                        merged_recurrence,
                    ),
                    sources=[],
                )
            if intent == "delete_event":
                try:
                    answer = calendar_service.delete_event(
                        merged_title, merged_date, merged_time, apply_to=merged_apply_to
                    )
                except CalendarDisambiguationError as exc:
                    set_pending(
                        PendingIntent(
                            intent=intent,
                            title=merged_title,
                            date=merged_date,
                            time=merged_time,
                            duration_minutes=merged_duration,
                            apply_to=merged_apply_to,
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
                recurrence=merged_recurrence,
                apply_to=merged_apply_to,
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
                date_str=merged_date,
                time_str=merged_time,
                duration_minutes=merged_duration,
                recurrence=merged_recurrence,
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
    recurrence = intent_data.get("recurrence") if isinstance(intent_data, dict) else None
    apply_to = intent_data.get("apply_to") if isinstance(intent_data, dict) else None
    if not isinstance(apply_to, str) or apply_to not in {"series", "single"}:
        apply_to = None
    duration_minutes = (
        intent_data.get("duration_minutes") if isinstance(intent_data, dict) else None
    )
    if not isinstance(duration_minutes, int) or duration_minutes <= 0:
        duration_minutes = None

    explicit_times = extract_explicit_times(message)
    range_start, range_end, range_ambiguous = extract_time_range(message)
    if time_str is None and range_ambiguous and intent in {"create_event", "update_event"}:
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

    if intent in {"create_event", "update_event", "delete_event", "query_calendar"}:
        if date_str is None:
            date_str = extract_date(message)

    if intent == "update_event" and time_str is None and len(explicit_times) >= 2:
        time_str = explicit_times[-1]
    if time_str is None and explicit_times:
        time_str = explicit_times[0]
    if (
        intent == "create_event"
        and time_str
        and duration_minutes is None
        and len(explicit_times) >= 2
        and date_str
    ):
        inferred_duration = _duration_from_end_time(
            date_str, time_str, explicit_times[-1]
        )
        if inferred_duration:
            duration_minutes = inferred_duration
    if intent in {"create_event", "update_event"} and range_start and range_end:
        if time_str is None:
            time_str = range_start
        if (
            intent == "create_event"
            and duration_minutes is None
            and (time_str == range_start)
        ):
            duration_minutes = _duration_between_times(range_start, range_end)

    if intent in {"create_event", "update_event"} and time_str is None and not explicit_times:
        parsed_time, time_ambiguous = extract_time(message)
        if time_ambiguous:
            set_pending(
                PendingIntent(
                    intent=intent,
                    title=title,
                    date=date_str,
                    time=None,
                    duration_minutes=duration_minutes,
                    recurrence=recurrence,
                    apply_to=apply_to,
                )
            )
            return AskResponse(
                model="calendar",
                answer=_build_ambiguous_time_message(parsed_time),
                sources=[],
            )
        time_str = parsed_time

    if intent == "create_event" and duration_minutes is None:
        duration_minutes = extract_duration_minutes(message)

    if apply_to is None:
        apply_to = _parse_apply_to(message)

    if recurrence is None:
        recurrence = _build_recurrence_from_message(message, date_str)
    if (
        recurrence
        and recurrence.get("frequency") == "weekly"
        and not recurrence.get("byweekday")
        and date_str
    ):
        try:
            weekday_idx = datetime.fromisoformat(date_str).weekday()
            weekday_codes = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
            recurrence["byweekday"] = [weekday_codes[weekday_idx]]
        except ValueError:
            pass

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
                        recurrence=recurrence,
                        apply_to=apply_to,
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
                        recurrence=recurrence,
                        apply_to=apply_to,
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
                if target.get("recurringEventId") and apply_to is None:
                    set_pending(
                        PendingIntent(
                            intent=intent,
                            title=title,
                            date=date_str,
                            time=time_str,
                            duration_minutes=duration_minutes,
                            recurrence=recurrence,
                            target=target,
                            awaiting_series_choice=True,
                        )
                    )
                    return AskResponse(
                        model="calendar",
                        answer=_build_series_choice_message(intent),
                        sources=[],
                    )
                set_pending(
                    PendingIntent(
                        intent=intent,
                        title=title,
                        date=date_str,
                        time=time_str,
                        duration_minutes=duration_minutes,
                        recurrence=recurrence,
                        apply_to=apply_to,
                        target=target,
                        awaiting_confirmation=True,
                    )
                )
                return AskResponse(
                    model="calendar",
                    answer=build_delete_confirmation_message(
                        target, scope=apply_to
                    ),
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
                    recurrence=recurrence,
                    apply_to=apply_to,
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
                    date_str=date_str,
                    time_str=time_str,
                    duration_minutes=duration_minutes,
                    recurrence=recurrence,
                ),
                sources=[],
            )

    if intent == "create_event":
        set_pending(
            PendingIntent(
                intent=intent,
                title=title,
                date=date_str,
                time=time_str,
                duration_minutes=duration_minutes,
                recurrence=recurrence,
                awaiting_confirmation=True,
            )
        )
        return AskResponse(
            model="calendar",
            answer=_build_create_update_confirmation_message(
                intent,
                title or "Untitled event",
                date_str,
                time_str,
                duration_minutes,
                recurrence,
            ),
            sources=[],
        )
    if intent == "query_calendar":
        clear_pending()
        try:
            answer = calendar_service.get_events(date_str, time_str)
        except CalendarActionError as exc:
            answer = str(exc)
        return AskResponse(model="calendar", answer=answer, sources=[])
    if intent == "update_event":
        set_pending(
            PendingIntent(
                intent=intent,
                title=title,
                date=date_str,
                time=time_str,
                recurrence=recurrence,
                apply_to=apply_to,
                awaiting_confirmation=True,
            )
        )
        return AskResponse(
            model="calendar",
            answer=_build_create_update_confirmation_message(
                intent,
                title or "Untitled event",
                date_str,
                time_str,
                duration_minutes,
                recurrence,
            ),
            sources=[],
        )
    if intent == "delete_event":
        try:
            candidates = calendar_service.find_event_candidates(title, date_str)
            if len(candidates) == 1:
                target = candidates[0]
                if target.get("recurringEventId") and apply_to is None:
                    set_pending(
                        PendingIntent(
                            intent=intent,
                            title=title,
                            date=date_str,
                            time=time_str,
                            duration_minutes=duration_minutes,
                            recurrence=recurrence,
                            target=target,
                            awaiting_series_choice=True,
                        )
                    )
                    return AskResponse(
                        model="calendar",
                        answer=_build_series_choice_message(intent),
                        sources=[],
                    )
                set_pending(
                    PendingIntent(
                        intent=intent,
                        title=title,
                        date=date_str,
                        time=time_str,
                        duration_minutes=duration_minutes,
                        recurrence=recurrence,
                        apply_to=apply_to,
                        target=target,
                        awaiting_confirmation=True,
                    )
                )
                return AskResponse(
                    model="calendar",
                    answer=build_delete_confirmation_message(
                        target, scope=apply_to
                    ),
                    sources=[],
                )
            answer = calendar_service.delete_event(
                title, date_str, time_str, apply_to=apply_to
            )
        except CalendarDisambiguationError as exc:
            set_pending(
                PendingIntent(
                    intent=intent,
                    title=title,
                    date=date_str,
                    time=time_str,
                    duration_minutes=duration_minutes,
                    apply_to=apply_to,
                    selection=exc.candidates,
                )
            )
            answer = str(exc)
        except CalendarActionError as exc:
            answer = str(exc)
        return AskResponse(model="calendar", answer=answer, sources=[])

    return None
