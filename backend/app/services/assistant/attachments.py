from __future__ import annotations

from dataclasses import dataclass
import re


_ATTACHMENT_HEADER_RE = re.compile(
    r"^\s*(sent with attachments\.?|attachments?:)\s*$", re.IGNORECASE
)
_FILENAME_RE = re.compile(r"^[\w\-. ()]+\.(pdf|docx|txt)\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class InlineAttachment:
    filename: str
    text: str
    source_type: str


def extract_inline_attachments(message: str) -> tuple[str, list[InlineAttachment]]:
    if not message:
        return message, []

    lines = message.splitlines()
    header_idx = None
    for idx, line in enumerate(lines):
        if _ATTACHMENT_HEADER_RE.match(line.strip()):
            header_idx = idx
            break

    if header_idx is None:
        max_scan_lines = min(len(lines), 8)
        candidate_idx = None
        for idx in range(max_scan_lines):
            line = lines[idx].strip()
            if not line:
                continue
            if _FILENAME_RE.match(line):
                candidate_idx = idx
                break
            break
        if candidate_idx is None:
            return message, []
        header_idx = candidate_idx

    filenames: list[str] = []
    cursor = header_idx + 1
    while cursor < len(lines) and not lines[cursor].strip():
        cursor += 1

    while cursor < len(lines):
        line = lines[cursor].strip()
        if not line:
            cursor += 1
            continue
        if _FILENAME_RE.match(line):
            filenames.append(line)
            cursor += 1
            continue
        break

    if not filenames:
        return message, []

    content = "\n".join(lines[cursor:]).strip()
    if not content:
        return message, []

    attachments = [
        InlineAttachment(
            filename=name,
            text=content,
            source_type=name.rsplit(".", 1)[-1].lower(),
        )
        for name in filenames
    ]
    cleaned_message = "\n".join(lines[:header_idx]).strip()
    return cleaned_message, attachments


def merge_attachment_text(attachments: list[InlineAttachment]) -> str:
    return "\n\n".join(a.text.strip() for a in attachments if a.text.strip()).strip()


def infer_note_title(attachments: list[InlineAttachment]) -> str | None:
    if not attachments:
        return None
    if len(attachments) == 1:
        return attachments[0].filename
    return "Uploaded notes"


def wants_note_action(message: str) -> bool:
    lowered = (message or "").lower()
    if not lowered.strip():
        return False
    triggers = [
        "take notes",
        "take a note",
        "make notes",
        "save notes",
        "save a note",
        "note this",
        "note that",
        "summarize",
        "summarise",
        "summary",
    ]
    return any(trigger in lowered for trigger in triggers)


def wants_extraction_action(message: str) -> bool:
    lowered = (message or "").lower()
    if not lowered.strip():
        return False
    triggers = [
        "extract",
        "split",
        "break into",
        "make notes",
        "make note",
        "create notes",
        "create note",
        "turn into notes",
        "turn into events",
        "create events",
        "add to calendar",
        "schedule",
    ]
    return any(trigger in lowered for trigger in triggers)


def attachments_to_sources(
    attachments: list[InlineAttachment],
    max_chars: int = 4000,
) -> list[dict[str, object]]:
    sources: list[dict[str, object]] = []
    for attachment in attachments:
        text = attachment.text or ""
        if max_chars and len(text) > max_chars:
            text = text[:max_chars].rstrip()
        sources.append(
            {
                "text": text,
                "metadata": {
                    "file_name": attachment.filename,
                    "source": "inline_attachment",
                    "source_type": attachment.source_type,
                },
                "score": 0.0,
            }
        )
    return sources
