from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Tuple

_TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", re.IGNORECASE)
_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_MD_SEP_RE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})\b")

_MONTHS = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}

_MONTH_DAY_RE = re.compile(
    r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?)\s+(\d{1,2})\b",
    re.IGNORECASE,
)
_TIME_RANGE_RE = re.compile(
    r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*(?:-|–|—|to)\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b",
    re.IGNORECASE,
)

_WEEKDAYS = {
    "monday": 0,
    "mon": 0,
    "tuesday": 1,
    "tue": 1,
    "tues": 1,
    "wednesday": 2,
    "wed": 2,
    "thursday": 3,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "friday": 4,
    "fri": 4,
    "saturday": 5,
    "sat": 5,
    "sunday": 6,
    "sun": 6,
}


def extract_time(text: str) -> Tuple[str | None, bool]:
    if not text:
        return None, False
    lowered = text.strip().lower()
    if not lowered:
        return None, False
    if re.search(r"\d{4}-\d{2}-\d{2}t", lowered):
        _, time_part = lowered.rsplit("t", 1)
        return extract_time(time_part)
    if "noon" in lowered:
        return "12:00", False
    if "midnight" in lowered:
        return "00:00", False

    for match in _TIME_RE.finditer(lowered):
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        meridiem = match.group(3)
        if minute > 59 or hour > 23:
            continue

        if meridiem:
            meridiem = meridiem.lower()
            if hour == 12:
                hour = 0 if meridiem == "am" else 12
            elif meridiem == "pm":
                hour += 12
            if hour > 23:
                continue
            return f"{hour:02d}:{minute:02d}", False

        if hour <= 12:
            return f"{hour:02d}:{minute:02d}", True

        return f"{hour:02d}:{minute:02d}", False

    return None, False


def extract_date(text: str, today: date | None = None) -> str | None:
    if not text:
        return None
    lowered = text.strip().lower()
    if not lowered:
        return None

    today_value = today or datetime.now().date()

    match = _DATE_RE.search(lowered)
    if match:
        try:
            parsed = date.fromisoformat(match.group(0))
            return parsed.isoformat()
        except ValueError:
            return None

    month_match = _MONTH_DAY_RE.search(lowered)
    if month_match:
        month = _MONTHS.get(month_match.group(1).lower())
        day = int(month_match.group(2))
        if month:
            try:
                candidate = date(today_value.year, month, day)
            except ValueError:
                candidate = None
            if candidate:
                if candidate < today_value:
                    try:
                        candidate = date(today_value.year + 1, month, day)
                    except ValueError:
                        return None
                return candidate.isoformat()

    md_match = _MD_SEP_RE.search(lowered)
    if md_match:
        month = int(md_match.group(1))
        day = int(md_match.group(2))
        try:
            candidate = date(today_value.year, month, day)
        except ValueError:
            candidate = None
        if candidate:
            if candidate < today_value:
                try:
                    candidate = date(today_value.year + 1, month, day)
                except ValueError:
                    return None
            return candidate.isoformat()

    if "today" in lowered:
        return today_value.isoformat()
    if "tomorrow" in lowered:
        return (today_value + timedelta(days=1)).isoformat()

    for name, weekday in _WEEKDAYS.items():
        if re.search(rf"\b{name}\b", lowered):
            days_ahead = (weekday - today_value.weekday()) % 7
            if days_ahead == 0 and "next" in lowered:
                days_ahead = 7
            return (today_value + timedelta(days=days_ahead)).isoformat()

    return None


def strip_temporal_tokens(text: str) -> str:
    if not text:
        return ""
    cleaned = _DATE_RE.sub(" ", text)
    cleaned = _TIME_RE.sub(" ", cleaned)
    for token in [
        "today",
        "tomorrow",
        "next",
        "january",
        "jan",
        "february",
        "feb",
        "march",
        "mar",
        "april",
        "apr",
        "may",
        "june",
        "jun",
        "july",
        "jul",
        "august",
        "aug",
        "september",
        "sep",
        "sept",
        "october",
        "oct",
        "november",
        "nov",
        "december",
        "dec",
        "monday",
        "mon",
        "tuesday",
        "tue",
        "tues",
        "wednesday",
        "wed",
        "thursday",
        "thu",
        "thur",
        "thurs",
        "friday",
        "fri",
        "saturday",
        "sat",
        "sunday",
        "sun",
        "noon",
        "midnight",
    ]:
        cleaned = re.sub(rf"\b{token}\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" ,")


def extract_duration_minutes(text: str) -> int | None:
    if not text:
        return None
    lowered = text.lower()
    if not lowered.strip():
        return None

    if "half hour" in lowered or "half an hour" in lowered:
        return 30

    hours_match = re.search(r"\b(\d+(?:\.\d+)?)\s*(h|hr|hrs|hour|hours)\b", lowered)
    minutes_match = re.search(r"\b(\d+)\s*(m|min|mins|minute|minutes)\b", lowered)

    total_minutes = 0
    found = False

    if hours_match:
        hours = float(hours_match.group(1))
        total_minutes += int(round(hours * 60))
        found = True

    if minutes_match:
        minutes = int(minutes_match.group(1))
        total_minutes += minutes
        found = True

    if found:
        return total_minutes if total_minutes > 0 else None

    return None


def extract_time_range(text: str) -> Tuple[str | None, str | None, bool]:
    if not text:
        return None, None, False
    lowered = text.lower()
    match = _TIME_RANGE_RE.search(lowered)
    if not match:
        return None, None, False

    start_hour = int(match.group(1))
    start_minute = int(match.group(2) or 0)
    start_meridiem = match.group(3)
    end_hour = int(match.group(4))
    end_minute = int(match.group(5) or 0)
    end_meridiem = match.group(6)

    if start_minute > 59 or end_minute > 59 or start_hour > 23 or end_hour > 23:
        return None, None, False

    if not start_meridiem and not end_meridiem:
        return None, None, True

    if not start_meridiem and end_meridiem:
        start_meridiem = end_meridiem
    if start_meridiem and not end_meridiem:
        end_meridiem = start_meridiem

    start_meridiem = start_meridiem.lower() if start_meridiem else None
    end_meridiem = end_meridiem.lower() if end_meridiem else None

    if not start_meridiem or not end_meridiem:
        return None, None, True

    if start_hour == 12:
        start_hour = 0 if start_meridiem == "am" else 12
    elif start_meridiem == "pm":
        start_hour += 12

    if end_hour == 12:
        end_hour = 0 if end_meridiem == "am" else 12
    elif end_meridiem == "pm":
        end_hour += 12

    if start_hour > 23 or end_hour > 23:
        return None, None, False

    return f"{start_hour:02d}:{start_minute:02d}", f"{end_hour:02d}:{end_minute:02d}", False


def extract_explicit_times(text: str) -> list[str]:
    if not text:
        return []
    lowered = text.lower()
    results: list[str] = []

    if "midnight" in lowered:
        results.append("00:00")
    if "noon" in lowered:
        results.append("12:00")

    for match in _TIME_RE.finditer(lowered):
        meridiem = match.group(3)
        if not meridiem:
            continue
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        if minute > 59 or hour > 23:
            continue
        meridiem = meridiem.lower()
        if hour == 12:
            hour = 0 if meridiem == "am" else 12
        elif meridiem == "pm":
            hour += 12
        if hour > 23:
            continue
        results.append(f"{hour:02d}:{minute:02d}")

    return results
