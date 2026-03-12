from __future__ import annotations

import json
from datetime import date, datetime, time
from typing import Any

from langchain_groq import ChatGroq

from app.core.settings import get_settings
from app.services.llm.prompt_templates import INTENT_PROMPT_TEMPLATE
from app.services.temporal_parser import extract_date, extract_time

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
        '{ "intent": "...", "title": "...", "content": "...", "date": "...", "time": "..." }'
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
