from __future__ import annotations

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

    if wants_extraction_action(intent_message):
        attachment_text = merge_attachment_text(attachments) if attachments else None
        if not attachment_text:
            cache = get_attachment_cache()
            attachment_text = cache.get("text")
        if attachment_text:
            return await extraction_handler.handle_extraction(
                instruction=intent_message, document_text=attachment_text
            )
        return AskResponse(
            model="assistant",
            answer="Please attach the document you want me to extract from.",
            sources=[],
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

    if intent == "chat":
        clear_pending()
        return await conversation_handler.handle_chat(intent_message)

    if attachments and intent == "rag_query":
        return await conversation_handler.handle_inline_rag(intent_message, attachments)

    return await conversation_handler.handle_rag_fallback(intent_message, payload.k)


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
