from __future__ import annotations

import json
from datetime import date, datetime, time
from typing import Any

from app.services.llm.groq_client import get_groq_chat_model
from app.services.llm.prompt_templates import build_extraction_prompt
from app.services.temporal_parser import extract_date, extract_duration_minutes, extract_time

MAX_NOTES = 20
MAX_EVENTS = 30
MAX_NOTE_TITLE = 120
MAX_NOTE_CONTENT = 5000
MAX_EVENT_DESCRIPTION = 2000


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


def _normalize_text(value: Any, max_len: int | None = None) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.strip().split())
    if not cleaned:
        return None
    if max_len:
        return cleaned[:max_len].rstrip()
    return cleaned


def _normalize_date(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    try:
        parsed = date.fromisoformat(cleaned)
        return parsed.isoformat()
    except ValueError:
        extracted = extract_date(cleaned)
        return extracted


def _normalize_time(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return None
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    try:
        parsed = time.fromisoformat(cleaned)
        return parsed.strftime("%H:%M")
    except ValueError:
        extracted, ambiguous = extract_time(cleaned)
        if ambiguous:
            return None
        return extracted


def _normalize_duration(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        minutes = int(value)
        return minutes if minutes > 0 else None
    if isinstance(value, str):
        return extract_duration_minutes(value)
    return None


def _normalize_notes(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    results: list[dict[str, Any]] = []
    for item in items[:MAX_NOTES]:
        if not isinstance(item, dict):
            continue
        title = _normalize_text(item.get("title"), MAX_NOTE_TITLE)
        content = _normalize_text(item.get("content"), MAX_NOTE_CONTENT)
        if not title or not content:
            continue
        snippet = _normalize_text(item.get("source_snippet"))
        results.append(
            {
                "title": title,
                "content": content,
                "source_snippet": snippet,
            }
        )
    return results


def _normalize_events(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    results: list[dict[str, Any]] = []
    for item in items[:MAX_EVENTS]:
        if not isinstance(item, dict):
            continue
        title = _normalize_text(item.get("title"))
        date_str = _normalize_date(item.get("date"))
        time_str = _normalize_time(item.get("time"))
        duration = _normalize_duration(item.get("duration_minutes"))
        description = _normalize_text(item.get("description"), MAX_EVENT_DESCRIPTION)
        if not title or not date_str:
            continue
        snippet = _normalize_text(item.get("source_snippet"))
        results.append(
            {
                "title": title,
                "date": date_str,
                "time": time_str,
                "duration_minutes": duration,
                "description": description,
                "source_snippet": snippet,
            }
        )
    return results


async def extract_notes_and_events(
    instruction: str, document: str
) -> dict[str, list[dict[str, Any]]]:
    llm = get_groq_chat_model()
    prompt = build_extraction_prompt(instruction=instruction, document=document)
    result = await llm.ainvoke(prompt)
    content = result.content if hasattr(result, "content") else str(result)
    if isinstance(content, list):
        content = " ".join(str(item) for item in content)
    data = _extract_json(str(content))
    notes = _normalize_notes(data.get("notes"))
    events = _normalize_events(data.get("events"))
    return {"notes": notes, "events": events}
