from __future__ import annotations


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


def _parse_confirmation(message: str) -> bool | None:
    lowered = message.strip().lower()
    if not lowered:
        return None
    if lowered in {"yes", "y", "confirm", "sure", "ok", "okay"}:
        return True
    if lowered in {"no", "n", "cancel", "stop"}:
        return False
    return None
