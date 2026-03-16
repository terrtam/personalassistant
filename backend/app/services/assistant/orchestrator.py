from __future__ import annotations

import re

from fastapi import HTTPException

from app.services.assistant.attachments import (
    extract_inline_attachments,
    infer_note_title,
    merge_attachment_text,
    wants_extraction_action,
    wants_note_action,
)
from app.services.attachments import extract_upload_text
from app.services.conversation_state import (
    clear_pending,
    get_attachment_cache,
    get_pending,
    set_attachment_cache,
)
from app.services.intent_detection import detect_intent
from app.services.llm.groq_client import get_groq_chat_model
from app.services.assistant.schemas import AskRequest, AskResponse, LLMSmokeRequest, LLMSmokeResponse
from app.services.assistant.handlers import calendar as calendar_handler
from app.services.assistant.handlers import conversation as conversation_handler
from app.services.assistant.handlers import extraction as extraction_handler
from app.services.assistant.handlers import notes as notes_handler
from app.services.assistant.notes_memory import extract_keywords, retrieve_notes_memory
from app.services import notes_service


def _is_memory_question(message: str) -> bool:
    cleaned = (message or "").strip().lower()
    if not cleaned:
        return False
    first_person_tokens = ["i ", " me ", " my ", " mine ", " do i ", " did i ", " am i "]
    if not any(token in f" {cleaned} " for token in first_person_tokens):
        return False
    if re.match(r"^(have|has)\s+i\b", cleaned):
        return True
    question_starters = (
        "what ",
        "which ",
        "who ",
        "when ",
        "where ",
        "why ",
        "how ",
        "do ",
        "did ",
        "can ",
        "should ",
        "is ",
        "are ",
        "was ",
        "were ",
        "have ",
        "has ",
    )
    if cleaned.endswith("?"):
        return True
    return cleaned.startswith(question_starters)


def _is_explicit_rag_request(message: str) -> bool:
    lowered = (message or "").lower()
    if not lowered.strip():
        return False
    patterns = [
        r"\bdocument\b",
        r"\bdoc\b",
        r"\bpdf\b",
        r"\bfile\b",
        r"\battachment\b",
        r"\battached\b",
        r"\bupload\b",
        r"\buploaded\b",
        r"\bsource\b",
        r"\bknowledge base\b",
        r"\bknowledge-base\b",
        r"\bkb\b",
        r"\bindex\b",
    ]
    return any(re.search(pattern, lowered) for pattern in patterns)


async def _try_answer_memory_question(message: str, k: int) -> AskResponse | None:
    sources = retrieve_notes_memory(message, k)
    if sources:
        clear_pending()
        return await conversation_handler.handle_rag_from_sources(message, sources)

    notes = notes_service.list_notes()
    if not notes:
        clear_pending()
        return AskResponse(
            model="assistant",
            answer="You don't have any notes yet.",
            sources=[],
        )

    keywords = extract_keywords(message)
    recent_notes = sorted(notes, key=lambda note: note.created_at, reverse=True)[:5]
    lines = ["**Possible Notes**", "I didn't find a direct match, but here are recent notes:"]
    for note in recent_notes:
        title = (note.title or "Untitled").strip()
        content = " ".join((note.content or "").split())
        if len(content) > 120:
            content = f"{content[:117]}..."
        created = note.created_at.astimezone().strftime("%a %b %d, %Y")
        lines.append(f"- **{title}**: {content} (_{created}_)")
    if keywords:
        lines.append(f'\nDo any of these relate to "{keywords[0]}"?')
    else:
        lines.append("\nDo any of these look relevant?")
    answer = "\n".join(lines)
    clear_pending()
    return AskResponse(model="assistant", answer=answer, sources=[])


async def handle_smoke(payload: LLMSmokeRequest) -> LLMSmokeResponse:
    try:
        clear_pending()
        llm = get_groq_chat_model()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Groq configuration error: {str(exc)}",
        ) from exc

    try:
        result = await llm.ainvoke(payload.prompt)
        content = result.content if hasattr(result, "content") else str(result)
        if isinstance(content, list):
            content = " ".join(str(item) for item in content)
        return LLMSmokeResponse(model=llm.model_name, response=str(content))
    except Exception as exc:
        message = str(exc).lower()
        status = 503 if any(token in message for token in ["timeout", "temporar", "unavailable", "rate limit", "overloaded"]) else 502
        raise HTTPException(
            status_code=status,
            detail="Groq provider request failed. Check API key, model, and network connectivity.",
        ) from exc


async def handle_ask(payload: AskRequest) -> AskResponse:
    message = payload.query or payload.question or ""
    cleaned_message, attachments = extract_inline_attachments(message)
    intent_message = cleaned_message or message

    if attachments:
        attachment_text = merge_attachment_text(attachments)
        attachment_names = [attachment.filename for attachment in attachments]
        set_attachment_cache(attachment_text or None, attachment_names or None)

    pending = get_pending()
    if pending is not None:
        response = extraction_handler.handle_pending(message, pending)
        if response is not None:
            return response

    if attachments and not cleaned_message.strip():
        attachment_text = merge_attachment_text(attachments)
        if attachment_text:
            intent_data = {
                "intent": "create_note",
                "title": infer_note_title(attachments),
                "content": attachment_text,
                "date": None,
                "time": None,
            }
            response = notes_handler.handle_intent(
                intent_message, "create_note", intent_data
            )
            if response is not None:
                return response

    pending = get_pending()
    if pending is not None:
        response = notes_handler.handle_pending(message, pending)
        if response is not None:
            return response
        response = calendar_handler.handle_pending(message, pending)
        if response is not None:
            return response

    if not attachments and _is_memory_question(intent_message):
        response = await _try_answer_memory_question(intent_message, payload.k)
        if response is not None:
            return response

    try:
        intent_data = detect_intent(intent_message)
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Groq configuration error: {str(exc)}",
        ) from exc
    except Exception as exc:
        message_lower = str(exc).lower()
        status = 503 if any(token in message_lower for token in ["timeout", "temporar", "unavailable", "rate limit", "overloaded"]) else 502
        raise HTTPException(
            status_code=status,
            detail="Groq provider request failed. Check API key, model, and network connectivity.",
        ) from exc

    intent = intent_data.get("intent")
    if intent == "needs_clarification":
        clear_pending()
        return AskResponse(
            model="assistant",
            answer="Could you clarify what you'd like me to do?",
            sources=[],
        )

    if intent == "rag_query" and not attachments and not _is_explicit_rag_request(intent_message):
        intent = "chat"
        intent_data["intent"] = "chat"

    if wants_extraction_action(intent_message):
        attachment_text = merge_attachment_text(attachments) if attachments else None
        if not attachment_text:
            cache = get_attachment_cache()
            attachment_text = cache.get("text")
        if attachment_text:
            return await extraction_handler.handle_extraction(
                instruction=intent_message, document_text=attachment_text
            )

    if attachments:
        if intent == "chat" and wants_note_action(intent_message):
            intent = "create_note"
            intent_data["intent"] = "create_note"
        if intent == "create_note" and not intent_data.get("content"):
            intent_data["content"] = merge_attachment_text(attachments)
            if not intent_data.get("title"):
                intent_data["title"] = infer_note_title(attachments)

    response = notes_handler.handle_intent(intent_message, intent, intent_data)
    if response is not None:
        return response

    response = calendar_handler.handle_intent(intent_message, intent, intent_data)
    if response is not None:
        return response

    if intent == "chat" and _is_memory_question(intent_message):
        response = await _try_answer_memory_question(intent_message, payload.k)
        if response is not None:
            return response

    if intent == "chat":
        clear_pending()
        return await conversation_handler.handle_chat(intent_message)

    if attachments and intent == "rag_query":
        return await conversation_handler.handle_inline_rag(intent_message, attachments)

    try:
        return await conversation_handler.handle_rag_fallback(
            intent_message, payload.k
        )
    except HTTPException as exc:
        if exc.status_code == 404 and not attachments:
            sources = retrieve_notes_memory(intent_message, payload.k)
            if sources:
                clear_pending()
                return await conversation_handler.handle_rag_from_sources(
                    intent_message, sources
                )
        raise


async def handle_ask_with_upload(
    file,
    question: str | None,
    query: str | None,
    k: int,
) -> AskResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required.")
    content = await file.read()
    text, _ = extract_upload_text(file.filename, content)
    if not text:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file has no extractable text content.",
        )
    set_attachment_cache(text, [file.filename])
    payload = AskRequest(question=question, query=query, k=k)
    return await handle_ask(payload)
