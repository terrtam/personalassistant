from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.llm.groq_client import get_groq_chat_model

router = APIRouter(prefix="/llm", tags=["llm"])


class LLMSmokeRequest(BaseModel):
    prompt: str = Field(..., min_length=1)


class LLMSmokeResponse(BaseModel):
    model: str
    response: str


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
