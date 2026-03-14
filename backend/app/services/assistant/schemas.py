from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class LLMSmokeRequest(BaseModel):
    prompt: str = Field(..., min_length=1)


class LLMSmokeResponse(BaseModel):
    model: str
    response: str


class AskRequest(BaseModel):
    question: str | None = Field(default=None, min_length=1)
    query: str | None = Field(default=None, min_length=1)
    k: int = Field(default=5, ge=1, le=20)

    @model_validator(mode="after")
    def _require_message(self) -> "AskRequest":
        if not (self.question or self.query):
            raise ValueError("question or query is required.")
        return self


class AskSource(BaseModel):
    text: str
    metadata: dict
    score: float


class AskResponse(BaseModel):
    model: str
    answer: str
    sources: list[AskSource]
