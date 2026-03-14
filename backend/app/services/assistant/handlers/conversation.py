from __future__ import annotations

from fastapi import HTTPException

from app.services.assistant.attachments import InlineAttachment, attachments_to_sources
from app.services.assistant.schemas import AskResponse, AskSource
from app.services.embeddings.pipeline import search_index
from app.services.llm.groq_client import get_groq_chat_model
from app.services.llm.prompt_templates import CHAT_PROMPT_TEMPLATE, build_rag_prompt


async def handle_chat(message: str) -> AskResponse:
    try:
        llm = get_groq_chat_model()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Groq configuration error: {str(exc)}",
        ) from exc

    prompt = CHAT_PROMPT_TEMPLATE.format(message=message.strip())
    try:
        result = await llm.ainvoke(prompt)
        content = result.content if hasattr(result, "content") else str(result)
        if isinstance(content, list):
            content = " ".join(str(item) for item in content)
        return AskResponse(model=llm.model_name, answer=str(content), sources=[])
    except Exception as exc:
        message_lower = str(exc).lower()
        status = 503 if any(token in message_lower for token in ["timeout", "temporar", "unavailable", "rate limit", "overloaded"]) else 502
        raise HTTPException(
            status_code=status,
            detail="Groq provider request failed. Check API key, model, and network connectivity.",
        ) from exc


async def handle_rag_fallback(message: str, k: int) -> AskResponse:
    try:
        llm = get_groq_chat_model()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Groq configuration error: {str(exc)}",
        ) from exc

    try:
        results = search_index(query=message, k=k)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to search embedding index: {str(exc)}",
        ) from exc

    if not results:
        raise HTTPException(
            status_code=404,
            detail="No relevant context found in embedding index.",
        )

    prompt = build_rag_prompt(question=message, sources=results)

    try:
        result = await llm.ainvoke(prompt)
        content = result.content if hasattr(result, "content") else str(result)
        if isinstance(content, list):
            content = " ".join(str(item) for item in content)
        return AskResponse(
            model=llm.model_name,
            answer=str(content),
            sources=[AskSource(**item) for item in results],
        )
    except Exception as exc:
        message = str(exc).lower()
        status = (
            503
            if any(
                token in message
                for token in [
                    "timeout",
                    "temporar",
                    "unavailable",
                    "rate limit",
                    "overloaded",
                ]
            )
            else 502
        )
        raise HTTPException(
            status_code=status,
            detail="Groq provider request failed. Check API key, model, and network connectivity.",
        ) from exc


async def handle_inline_rag(
    message: str, attachments: list[InlineAttachment]
) -> AskResponse:
    try:
        llm = get_groq_chat_model()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Groq configuration error: {str(exc)}",
        ) from exc

    sources = attachments_to_sources(attachments)
    question = message.strip() or "Summarize the attached document."
    prompt = build_rag_prompt(question=question, sources=sources)

    try:
        result = await llm.ainvoke(prompt)
        content = result.content if hasattr(result, "content") else str(result)
        if isinstance(content, list):
            content = " ".join(str(item) for item in content)
        return AskResponse(
            model=llm.model_name,
            answer=str(content),
            sources=[AskSource(**item) for item in sources],
        )
    except Exception as exc:
        message_lower = str(exc).lower()
        status = (
            503
            if any(
                token in message_lower
                for token in ["timeout", "temporar", "unavailable", "rate limit", "overloaded"]
            )
            else 502
        )
        raise HTTPException(
            status_code=status,
            detail="Groq provider request failed. Check API key, model, and network connectivity.",
        ) from exc
