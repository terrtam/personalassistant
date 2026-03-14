"""
LLM API router.

Defines endpoints that handle user messages and route them through the
assistant pipeline. Requests are analyzed for intent and dispatched to
the appropriate services such as calendar operations, note management,
or general conversational responses.
"""

from fastapi import APIRouter, File, Form, UploadFile
from fastapi import HTTPException

from app.services.assistant.orchestrator import handle_ask, handle_smoke, handle_ask_with_upload
from app.services.assistant.schemas import (
    AskRequest,
    AskResponse,
    LLMSmokeRequest,
    LLMSmokeResponse,
)

router = APIRouter(prefix="/llm", tags=["llm"])


@router.post("/smoke", response_model=LLMSmokeResponse)
async def smoke_test_llm(payload: LLMSmokeRequest) -> LLMSmokeResponse:
    return await handle_smoke(payload)


@router.post("/ask", response_model=AskResponse)
async def ask_question(payload: AskRequest) -> AskResponse:
    return await handle_ask(payload)


@router.post("/ask/upload", response_model=AskResponse)
async def ask_question_upload(
    file: UploadFile = File(...),
    question: str | None = Form(default=None),
    query: str | None = Form(default=None),
    k: int = Form(default=5),
) -> AskResponse:
    if not question and not query:
        raise HTTPException(status_code=400, detail="question or query is required.")
    return await handle_ask_with_upload(
        file=file,
        question=question,
        query=query,
        k=k,
    )
