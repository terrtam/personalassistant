from __future__ import annotations

import json
from datetime import date, datetime, time
from typing import Any

from langchain_groq import ChatGroq

from app.core.settings import get_settings
from app.services.llm.prompt_templates import INTENT_PROMPT_TEMPLATE
from app.services.temporal_parser import extract_date, extract_duration_minutes, extract_time

ALLOWED_INTENTS = {
    "create_event",
    "query_calendar",
    "query_notes",
    "update_event",
    "delete_event",
    "create_note",
    "update_note",
    "delete_note",
    "rag_query",
    "needs_clarification",
    "chat",
}

DEFAULT_INTENT_PAYLOAD: dict[str, Any] = {
    "intent": "chat",
    "title": None,
    "content": None,
    "date": None,
    "time": None,
    "duration_minutes": None,
    "recurrence": None,
    "apply_to": None,
}


def _get_intent_llm() -> ChatGroq:
    settings = get_settings()
    return ChatGroq(
        model=settings.groq_model,
        temperature=0.0,
        timeout=settings.groq_timeout_seconds,
        groq_api_key=settings.groq_api_key,
    )


def _build_prompt(user_message: str) -> str:
    today = datetime.now().date().isoformat()
    schema_hint = (
        '{ "intent": "...", "title": "...", "content": "...", "date": "...", "time": "...", "duration_minutes": 60, "recurrence": {"frequency": "weekly", "interval": 1, "byweekday": ["wednesday"], "ends": {"type": "never", "date": null, "count": null}}, "apply_to": "series" }'
    )
    return (
        f"{INTENT_PROMPT_TEMPLATE}\n\n"
        f"Today is {today}.\n"
        "If a field is missing, use null.\n"
        f"JSON format:\n{schema_hint}\n\n"
        f"User message: {user_message.strip()}"
    )


def _extract_json(payload: str) -> dict[str, Any]:
    if not payload:
        return {}
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        start = payload.find("{")
        end = payload.rfind("}")
        if start != -1 and end != -1 and end > start:
            snippet = payload[start : end + 1]
            try:
                return json.loads(snippet)
            except json.JSONDecodeError:
                return {}
    return {}


def _normalize_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _normalize_date(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    try:
        parsed = date.fromisoformat(cleaned)
    except ValueError:
        candidate = cleaned
        if candidate.endswith("Z"):
            candidate = candidate[:-1] + "+00:00"
        try:
            parsed_dt = datetime.fromisoformat(candidate)
            parsed = parsed_dt.date()
        except ValueError:
            extracted = extract_date(cleaned)
            return extracted
    return parsed.isoformat()


def _normalize_time(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    try:
        parsed = time.fromisoformat(cleaned)
    except ValueError:
        extracted, ambiguous = extract_time(cleaned)
        if ambiguous:
            return None
        return extracted
    return parsed.strftime("%H:%M")


def _normalize_duration(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        minutes = int(value)
        return minutes if minutes > 0 else None
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned.isdigit():
            minutes = int(cleaned)
            return minutes if minutes > 0 else None
        return extract_duration_minutes(cleaned)
    return None


def _normalize_positive_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        parsed = int(value)
        return parsed if parsed > 0 else None
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned.isdigit():
            parsed = int(cleaned)
            return parsed if parsed > 0 else None
    return None


_WEEKDAY_CODES = {
    "monday": "MO",
    "mon": "MO",
    "tuesday": "TU",
    "tue": "TU",
    "tues": "TU",
    "wednesday": "WE",
    "wed": "WE",
    "thursday": "TH",
    "thu": "TH",
    "thur": "TH",
    "thurs": "TH",
    "friday": "FR",
    "fri": "FR",
    "saturday": "SA",
    "sat": "SA",
    "sunday": "SU",
    "sun": "SU",
}


def _normalize_byweekday(value: Any) -> list[str] | None:
    if value is None:
        return None
    tokens: list[str] = []
    if isinstance(value, str):
        raw_tokens = value.replace(",", " ").split()
        tokens = raw_tokens
    elif isinstance(value, list):
        tokens = [str(item) for item in value if item is not None]
    else:
        return None

    codes: list[str] = []
    for token in tokens:
        cleaned = token.strip().lower()
        if not cleaned:
            continue
        if cleaned in {"mo", "tu", "we", "th", "fr", "sa", "su"}:
            code = cleaned.upper()
        else:
            code = _WEEKDAY_CODES.get(cleaned)
        if code and code not in codes:
            codes.append(code)
    return codes or None


def _normalize_recurrence(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None

    frequency_raw = value.get("frequency")
    frequency = (
        frequency_raw.strip().lower()
        if isinstance(frequency_raw, str)
        else None
    )
    if frequency not in {"daily", "weekly", "monthly", "yearly"}:
        return None

    interval = _normalize_positive_int(value.get("interval")) or 1
    byweekday = _normalize_byweekday(value.get("byweekday"))

    ends_raw = value.get("ends")
    ends: dict[str, Any] | None = None
    if isinstance(ends_raw, dict):
        ends_type_raw = ends_raw.get("type") or ends_raw.get("ends")
        ends_type = (
            ends_type_raw.strip().lower()
            if isinstance(ends_type_raw, str)
            else None
        )
        if ends_type in {"never", "on", "date", "until", "after", "count"}:
            if ends_type in {"date", "until"}:
                ends_type = "on"
            if ends_type == "count":
                ends_type = "after"
            ends = {"type": ends_type, "date": None, "count": None}
            if ends_type == "on":
                ends["date"] = _normalize_date(ends_raw.get("date"))
            if ends_type == "after":
                ends["count"] = _normalize_positive_int(ends_raw.get("count"))

    return {
        "frequency": frequency,
        "interval": interval,
        "byweekday": byweekday,
        "ends": ends or {"type": "never", "date": None, "count": None},
    }


def _normalize_apply_to(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip().lower()
    if cleaned in {"series", "single"}:
        return cleaned
    return None


def _normalize_payload(data: dict[str, Any]) -> dict[str, Any]:
    result = dict(DEFAULT_INTENT_PAYLOAD)
    if not isinstance(data, dict):
        return result

    intent_raw = data.get("intent")
    if isinstance(intent_raw, str):
        intent = intent_raw.strip().lower()
        if intent in ALLOWED_INTENTS:
            result["intent"] = intent

    result["title"] = _normalize_text(data.get("title"))
    result["content"] = _normalize_text(data.get("content"))
    result["date"] = _normalize_date(data.get("date"))
    result["time"] = _normalize_time(data.get("time"))
    result["duration_minutes"] = _normalize_duration(data.get("duration_minutes"))
    result["recurrence"] = _normalize_recurrence(data.get("recurrence"))
    result["apply_to"] = _normalize_apply_to(data.get("apply_to"))
    return result


def detect_intent(user_message: str) -> dict[str, Any]:
    cleaned = (user_message or "").strip()
    if not cleaned:
        return dict(DEFAULT_INTENT_PAYLOAD)

    llm = _get_intent_llm()
    prompt = _build_prompt(cleaned)
    response = llm.invoke(prompt)
    content = response.content if hasattr(response, "content") else str(response)
    if isinstance(content, list):
        content = " ".join(str(item) for item in content)
    data = _extract_json(str(content))
    return _normalize_payload(data)
