from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from googleapiclient.errors import HttpError

from app.core.settings import get_settings
from app.services.calendar.google_calendar import (
    GoogleCalendarConfigError,
    create_event as google_create_event,
    delete_event as google_delete_event,
    list_events as google_list_events,
    update_event as google_update_event,
)

DEFAULT_EVENT_DURATION_MINUTES = 60
DEFAULT_QUERY_WINDOW_DAYS = 7
DEFAULT_SEARCH_WINDOW_DAYS = 30


class CalendarActionError(RuntimeError):
    """Raised when a calendar action fails or needs clarification."""


class CalendarConflictError(CalendarActionError):
    """Raised when a calendar event overlaps another."""


class CalendarDisambiguationError(CalendarActionError):
    """Raised when multiple events match and user needs to choose."""

    def __init__(self, message: str, candidates: list[dict[str, Any]]) -> None:
        super().__init__(message)
        self.candidates = candidates


def _local_tz():
    tzinfo = datetime.now().astimezone().tzinfo
    return tzinfo


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _parse_time(value: str) -> time:
    return time.fromisoformat(value)


def _combine_date_time(date_str: str, time_str: str) -> datetime:
    tzinfo = _local_tz()
    return datetime.combine(_parse_date(date_str), _parse_time(time_str), tzinfo=tzinfo)


def _parse_event_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if "T" not in cleaned:
        try:
            parsed_date = date.fromisoformat(cleaned)
        except ValueError:
            return None
        return datetime.combine(parsed_date, time.min, tzinfo=_local_tz())
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError:
        return None


def _event_duration(event: dict[str, Any]) -> timedelta:
    start = _parse_event_datetime(event.get("start", {}).get("dateTime"))
    if not start:
        start = _parse_event_datetime(event.get("start", {}).get("date"))
    end = _parse_event_datetime(event.get("end", {}).get("dateTime"))
    if not end:
        end = _parse_event_datetime(event.get("end", {}).get("date"))
    if start and end and end > start:
        return end - start
    return timedelta(minutes=DEFAULT_EVENT_DURATION_MINUTES)


def _format_datetime(dt: datetime) -> str:
    return dt.strftime("%a %b %d, %Y at %H:%M %Z").strip()


def _format_event_line(event: dict[str, Any]) -> str:
    summary = event.get("summary") or "Untitled event"
    start_info = event.get("start", {}) if isinstance(event.get("start"), dict) else {}
    if "dateTime" in start_info:
        dt = _parse_event_datetime(start_info.get("dateTime"))
        when = _format_datetime(dt) if dt else str(start_info.get("dateTime"))
    elif "date" in start_info:
        when = f"{start_info.get('date')} (all day)"
    else:
        when = "time unknown"
    return f"- **{summary}** - _{when}_"


def _format_event_choice(index: int, event: dict[str, Any]) -> str:
    summary = event.get("summary") or "Untitled event"
    start_info = event.get("start", {}) if isinstance(event.get("start"), dict) else {}
    if "dateTime" in start_info:
        dt = _parse_event_datetime(start_info.get("dateTime"))
        when = _format_datetime(dt) if dt else str(start_info.get("dateTime"))
    elif "date" in start_info:
        when = f"{start_info.get('date')} (all day)"
    else:
        when = "time unknown"
    event_id = event.get("id") or ""
    short_id = event_id[-6:] if event_id else "unknown"
    return f"{index}) **{summary}** - _{when}_ (id: `{short_id}`)"


def _format_conflicts(conflicts: list[dict[str, Any]]) -> str:
    lines = [_format_event_line(event) for event in conflicts]
    return "\n".join(lines)


def _build_conflict_message(action: str, conflicts: list[dict[str, Any]]) -> str:
    intro = "**Scheduling Conflict**\nThe requested time overlaps with:"
    if action == "update":
        follow_up = "*What time should I move it to instead?*"
    else:
        follow_up = "*What time should I use instead?*"
    return f"{intro}\n{_format_conflicts(conflicts)}\n\n{follow_up}"


def _candidate_from_event(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": event.get("id"),
        "summary": event.get("summary"),
        "start": event.get("start"),
        "end": event.get("end"),
    }


def _build_selection_message(title: str, candidates: list[dict[str, Any]]) -> str:
    header = f'**Multiple Matches**\nEvents named "{title}" were found.'
    lines = [header, "Reply with the number or the id shown."]
    for idx, candidate in enumerate(candidates, start=1):
        lines.append(_format_event_choice(idx, candidate))
    return "\n".join(lines)


def _candidate_start_date(candidate: dict[str, Any]) -> str | None:
    start_info = candidate.get("start") or {}
    if isinstance(start_info, dict):
        raw = start_info.get("dateTime") or start_info.get("date")
    else:
        raw = None
    if not raw:
        return None
    try:
        if "T" in str(raw):
            return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).date().isoformat()
        return datetime.fromisoformat(str(raw)).date().isoformat()
    except ValueError:
        return None


def find_event_candidates(
    title: str | None,
    target_date: str | None = None,
) -> list[dict[str, Any]]:
    if not title:
        return []
    settings = get_settings()
    window_start = datetime.now(_local_tz())
    window_end = window_start + timedelta(days=DEFAULT_SEARCH_WINDOW_DAYS)
    try:
        events = google_list_events(
            calendar_id=settings.google_calendar_id,
            time_min=window_start,
            time_max=window_end,
            max_results=25,
        )
    except Exception as exc:
        raise _handle_calendar_error(exc) from exc

    matches = _filter_events_by_title(events, title)
    candidates = [_candidate_from_event(event) for event in matches]
    if target_date:
        candidates = [
            candidate
            for candidate in candidates
            if _candidate_start_date(candidate) == target_date
        ]

    deduped: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        key = candidate.get("id") or f"{candidate.get('summary')}:{candidate.get('start')}"
        if key not in deduped:
            deduped[key] = candidate
    return list(deduped.values())


def build_disambiguation_message(
    title: str, candidates: list[dict[str, Any]]
) -> str:
    return _build_selection_message(title, candidates)


def build_delete_confirmation_message(candidate: dict[str, Any]) -> str:
    summary = candidate.get("summary") or "Untitled event"
    start_info = candidate.get("start", {}) if isinstance(candidate.get("start"), dict) else {}
    if "dateTime" in start_info:
        dt = _parse_event_datetime(start_info.get("dateTime"))
        when = _format_datetime(dt) if dt else str(start_info.get("dateTime"))
    elif "date" in start_info:
        when = f"{start_info.get('date')} (all day)"
    else:
        when = "time unknown"
    return (
        "**Confirm Delete**\n"
        f"- **Title:** {summary}\n"
        f"- **When:** _{when}_\n\n"
        "Reply `yes` to confirm or `no` to cancel."
    )


def _format_events_summary(events: list[dict[str, Any]]) -> str:
    if not events:
        return "You have no upcoming events."
    lines = [_format_event_line(event) for event in events]
    return "**Upcoming Events**\n" + "\n".join(lines)


def _filter_events_by_title(
    events: list[dict[str, Any]], title: str | None
) -> list[dict[str, Any]]:
    if not title:
        return []
    title_lower = title.lower()
    return [
        event
        for event in events
        if title_lower in (event.get("summary") or "").lower()
    ]


def _filter_events_by_time(
    events: list[dict[str, Any]],
    target_time: time,
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for event in events:
        start_info = event.get("start", {}) if isinstance(event.get("start"), dict) else {}
        start_value = start_info.get("dateTime") or start_info.get("date")
        start_dt = _parse_event_datetime(start_value)
        if not start_dt:
            continue
        if start_dt.time().hour == target_time.hour and start_dt.time().minute == target_time.minute:
            filtered.append(event)
    return filtered


def _find_conflicts(
    start: datetime,
    end: datetime,
    exclude_event_id: str | None = None,
) -> list[dict[str, Any]]:
    settings = get_settings()
    try:
        events = google_list_events(
            calendar_id=settings.google_calendar_id,
            time_min=start,
            time_max=end,
            max_results=25,
        )
    except Exception as exc:
        raise _handle_calendar_error(exc) from exc

    conflicts: list[dict[str, Any]] = []
    for event in events:
        if event.get("status") == "cancelled":
            continue
        event_id = event.get("id")
        if exclude_event_id and event_id == exclude_event_id:
            continue
        conflicts.append(event)
    return conflicts


def _handle_calendar_error(exc: Exception) -> CalendarActionError:
    if isinstance(exc, GoogleCalendarConfigError):
        return CalendarActionError(str(exc))
    if isinstance(exc, HttpError):
        status_code = getattr(exc, "status_code", None)
        if status_code is None and getattr(exc, "resp", None) is not None:
            status_code = getattr(exc.resp, "status", None)
        suffix = f" (status {status_code})" if status_code else ""
        return CalendarActionError(f"Google Calendar request failed{suffix}.")
    return CalendarActionError("Calendar request failed. Please try again.")


def create_event(
    title: str | None,
    date_str: str,
    time_str: str,
    duration_minutes: int | None,
    description: str | None = None,
) -> str:
    settings = get_settings()
    summary = title.strip() if isinstance(title, str) and title.strip() else "Untitled event"
    try:
        start = _combine_date_time(date_str, time_str)
        if not duration_minutes or duration_minutes <= 0:
            raise CalendarActionError(
                "When should the event end? (You can also say a duration like 45 minutes.)"
            )
        end = start + timedelta(minutes=duration_minutes)
        conflicts = _find_conflicts(start, end)
        if conflicts:
            raise CalendarConflictError(_build_conflict_message("create", conflicts))
        event = google_create_event(
            calendar_id=settings.google_calendar_id,
            summary=summary,
            start=start,
            end=end,
            description=description,
        )
    except CalendarActionError:
        raise
    except Exception as exc:
        raise _handle_calendar_error(exc) from exc

    rendered_summary = event.get("summary") or summary
    return (
        "**Event Scheduled**\n"
        f"- **Title:** {rendered_summary}\n"
        f"- **When:** _{_format_datetime(start)} to {_format_datetime(end)}_"
    )


def get_events(date_str: str | None = None, time_str: str | None = None) -> str:
    settings = get_settings()
    tzinfo = _local_tz()
    try:
        if date_str:
            start = datetime.combine(_parse_date(date_str), time.min, tzinfo=tzinfo)
            end = start + timedelta(days=DEFAULT_QUERY_WINDOW_DAYS)
        else:
            start = datetime.now(tzinfo)
            end = start + timedelta(days=DEFAULT_QUERY_WINDOW_DAYS)
        events = google_list_events(
            calendar_id=settings.google_calendar_id,
            time_min=start,
            time_max=end,
            max_results=25,
        )
    except Exception as exc:
        raise _handle_calendar_error(exc) from exc

    _ = time_str  # Reserved for future time-scoped queries.
    return _format_events_summary(events)


def update_event(title: str | None, date_str: str, time_str: str) -> str:
    if not title:
        raise CalendarActionError("Which event should I move?")
    settings = get_settings()
    new_start = _combine_date_time(date_str, time_str)
    window_start = datetime.now(_local_tz())
    window_end = window_start + timedelta(days=DEFAULT_SEARCH_WINDOW_DAYS)

    try:
        events = google_list_events(
            calendar_id=settings.google_calendar_id,
            time_min=window_start,
            time_max=window_end,
            max_results=25,
        )
        matches = _filter_events_by_title(events, title)
        if not matches:
            raise CalendarActionError(f'I could not find an event titled "{title}".')
        if len(matches) > 1:
            candidates = [_candidate_from_event(event) for event in matches]
            raise CalendarDisambiguationError(
                _build_selection_message(title, candidates),
                candidates,
            )
        target = matches[0]
        event_id = target.get("id")
        if not event_id:
            raise CalendarActionError("Found the event but it has no ID to update.")
        duration = _event_duration(target)
        new_end = new_start + duration
        conflicts = _find_conflicts(new_start, new_end, exclude_event_id=event_id)
        if conflicts:
            raise CalendarConflictError(_build_conflict_message("update", conflicts))
        updated = google_update_event(
            calendar_id=settings.google_calendar_id,
            event_id=event_id,
            start=new_start,
            end=new_end,
        )
    except CalendarActionError:
        raise
    except Exception as exc:
        raise _handle_calendar_error(exc) from exc

    rendered_summary = updated.get("summary") or title
    return (
        "**Event Updated**\n"
        f"- **Title:** {rendered_summary}\n"
        f"- **New time:** _{_format_datetime(new_start)}_"
    )


def delete_event(title: str | None, date_str: str, time_str: str) -> str:
    if not title:
        raise CalendarActionError("Which event should I cancel?")
    settings = get_settings()
    target_date = _parse_date(date_str)
    tzinfo = _local_tz()
    window_start = datetime.combine(target_date, time.min, tzinfo=tzinfo)
    window_end = window_start + timedelta(days=1)

    try:
        events = google_list_events(
            calendar_id=settings.google_calendar_id,
            time_min=window_start,
            time_max=window_end,
            max_results=25,
        )
        matches = _filter_events_by_title(events, title)
        if time_str:
            matches = _filter_events_by_time(matches, _parse_time(time_str))
        if not matches:
            raise CalendarActionError(f'I could not find "{title}" on that date.')
        if len(matches) > 1:
            candidates = [_candidate_from_event(event) for event in matches]
            raise CalendarDisambiguationError(
                _build_selection_message(title, candidates),
                candidates,
            )
        target = matches[0]
        event_id = target.get("id")
        if not event_id:
            raise CalendarActionError("Found the event but it has no ID to cancel.")
        google_delete_event(
            calendar_id=settings.google_calendar_id,
            event_id=event_id,
        )
    except CalendarActionError:
        raise
    except Exception as exc:
        raise _handle_calendar_error(exc) from exc

    return "**Event Canceled**\n" f"- **Title:** {title}"


def update_event_from_candidate(
    candidate: dict[str, Any], date_str: str, time_str: str
) -> str:
    event_id = candidate.get("id")
    if not event_id:
        raise CalendarActionError("Found the event but it has no ID to update.")
    summary = candidate.get("summary") or "Untitled event"
    new_start = _combine_date_time(date_str, time_str)
    duration = _event_duration(candidate)
    new_end = new_start + duration
    conflicts = _find_conflicts(new_start, new_end, exclude_event_id=event_id)
    if conflicts:
        raise CalendarConflictError(_build_conflict_message("update", conflicts))
    try:
        updated = google_update_event(
            calendar_id=get_settings().google_calendar_id,
            event_id=event_id,
            start=new_start,
            end=new_end,
        )
    except Exception as exc:
        raise _handle_calendar_error(exc) from exc
    rendered_summary = updated.get("summary") or summary
    return (
        "**Event Updated**\n"
        f"- **Title:** {rendered_summary}\n"
        f"- **New time:** _{_format_datetime(new_start)}_"
    )


def delete_event_from_candidate(candidate: dict[str, Any]) -> str:
    event_id = candidate.get("id")
    if not event_id:
        raise CalendarActionError("Found the event but it has no ID to cancel.")
    summary = candidate.get("summary") or "Untitled event"
    try:
        google_delete_event(
            calendar_id=get_settings().google_calendar_id,
            event_id=event_id,
        )
    except Exception as exc:
        raise _handle_calendar_error(exc) from exc
    return "**Event Canceled**\n" f"- **Title:** {summary}"
