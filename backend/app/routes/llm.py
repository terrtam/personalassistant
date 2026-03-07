from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.embeddings.pipeline import search_index
from app.services.llm.groq_client import get_groq_chat_model
from app.services.llm.prompt_templates import build_rag_prompt

router = APIRouter(prefix="/llm", tags=["llm"])


class LLMSmokeRequest(BaseModel):
    prompt: str = Field(..., min_length=1)


class LLMSmokeResponse(BaseModel):
    model: str
    response: str


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1)
    k: int = Field(default=5, ge=1, le=20)


class AskSource(BaseModel):
    text: str
    metadata: dict
    score: float


class AskResponse(BaseModel):
    model: str
    answer: str
    sources: list[AskSource]


@router.post("/smoke", response_model=LLMSmokeResponse)
async def smoke_test_llm(payload: LLMSmokeRequest) -> LLMSmokeResponse:
    try:
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


@router.post("/ask", response_model=AskResponse)
async def ask_question(payload: AskRequest) -> AskResponse:
    try:
        llm = get_groq_chat_model()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Groq configuration error: {str(exc)}",
        ) from exc

    try:
        results = search_index(query=payload.question, k=payload.k)
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

    prompt = build_rag_prompt(question=payload.question, sources=results)

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
