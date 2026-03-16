from __future__ import annotations

from math import sqrt
from typing import Any

from app.services import notes_service
from app.services.embeddings.embedding_client import get_embedding_model


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    if len(left) != len(right):
        return 0.0
    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for l_val, r_val in zip(left, right, strict=False):
        dot += l_val * r_val
        left_norm += l_val * l_val
        right_norm += r_val * r_val
    denom = sqrt(left_norm) * sqrt(right_norm)
    if denom == 0.0:
        return 0.0
    return dot / denom


def _note_to_text(note: notes_service.Note) -> str:
    title = (note.title or "").strip()
    content = (note.content or "").strip()
    if title and content:
        return f"Title: {title}\nContent: {content}"
    return title or content


def retrieve_notes_memory(query: str, k: int = 5) -> list[dict[str, Any]]:
    cleaned_query = (query or "").strip()
    if not cleaned_query:
        return []

    notes = notes_service.list_notes()
    if not notes:
        return []

    texts = [_note_to_text(note) for note in notes]
    if not any(texts):
        return []

    embeddings = get_embedding_model()
    query_vec = embeddings.embed_query(cleaned_query)
    note_vecs = embeddings.embed_documents(texts)

    scored: list[dict[str, Any]] = []
    for note, text, vec in zip(notes, texts, note_vecs, strict=False):
        if not text:
            continue
        score = _cosine_similarity(query_vec, vec)
        if score <= 0.0:
            continue
        scored.append(
            {
                "text": text,
                "metadata": {
                    "source": "note",
                    "title": note.title,
                    "note_id": note.id,
                    "created_at": note.created_at.isoformat(),
                },
                "score": float(score),
            }
        )

    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[: max(1, k)]
