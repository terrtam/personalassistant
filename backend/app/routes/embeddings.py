from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.settings import get_settings
from app.services.embeddings.pipeline import build_index, search_index

router = APIRouter(prefix="/embeddings", tags=["embeddings"])


class EmbeddingDocument(BaseModel):
    id: str | None = None
    text: str = Field(..., min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BuildIndexRequest(BaseModel):
    documents: list[EmbeddingDocument] = Field(..., min_length=1)
    chunk_size: int | None = Field(default=None, ge=100, le=4000)
    chunk_overlap: int | None = Field(default=None, ge=0, le=1000)


class BuildIndexResponse(BaseModel):
    provider: str
    model: str
    index_path: str
    source_documents: int
    chunks: int


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    k: int = Field(default=5, ge=1, le=20)


class SearchResult(BaseModel):
    text: str
    metadata: dict[str, Any]
    score: float


class SearchResponse(BaseModel):
    results: list[SearchResult]


@router.post("/index", response_model=BuildIndexResponse)
async def index_embeddings(payload: BuildIndexRequest) -> BuildIndexResponse:
    try:
        counts = build_index(
            documents=[doc.model_dump() for doc in payload.documents],
            chunk_size=payload.chunk_size,
            chunk_overlap=payload.chunk_overlap,
        )
        settings = get_settings()
        return BuildIndexResponse(
            provider=settings.embedding_provider,
            model=settings.embedding_model,
            index_path=settings.embedding_index_path,
            source_documents=counts["source_documents"],
            chunks=counts["chunks"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to build embedding index: {str(exc)}",
        ) from exc


@router.post("/search", response_model=SearchResponse)
async def search_embeddings(payload: SearchRequest) -> SearchResponse:
    try:
        results = search_index(query=payload.query, k=payload.k)
        return SearchResponse(
            results=[SearchResult(**item) for item in results],
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to search embedding index: {str(exc)}",
        ) from exc
