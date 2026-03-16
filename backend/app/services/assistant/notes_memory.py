from __future__ import annotations

from math import sqrt
import re
from typing import Any

from app.services import notes_service
from app.core.settings import get_settings
from app.services.embeddings.embedding_client import get_embedding_model

_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "but",
    "by",
    "did",
    "do",
    "does",
    "for",
    "from",
    "had",
    "has",
    "have",
    "i",
    "in",
    "is",
    "it",
    "like",
    "me",
    "my",
    "of",
    "on",
    "or",
    "about",
    "mention",
    "mentioned",
    "saying",
    "say",
    "says",
    "said",
    "tell",
    "told",
    "talk",
    "talked",
    "shared",
    "that",
    "the",
    "their",
    "there",
    "this",
    "to",
    "was",
    "were",
    "what",
    "when",
    "where",
    "who",
    "why",
    "with",
    "you",
    "your",
}


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


def extract_keywords(query: str) -> list[str]:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", (query or "").lower())
    tokens = [token for token in cleaned.split() if token and token not in _STOPWORDS]
    seen = set()
    keywords: list[str] = []
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        keywords.append(token)
    return keywords


def _keyword_match_score(text: str, keywords: list[str]) -> int:
    if not text or not keywords:
        return 0
    lowered = text.lower()
    return sum(1 for keyword in keywords if keyword in lowered)


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

    settings = get_settings()
    min_score = max(0.0, float(settings.embedding_min_semantic_score))

    try:
        embeddings = get_embedding_model()
        query_vec = embeddings.embed_query(cleaned_query)
        note_vecs = embeddings.embed_documents(texts)
    except Exception:
        note_vecs = []
        query_vec = []

    scored: list[dict[str, Any]] = []
    if note_vecs and query_vec:
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

    if scored:
        scored.sort(key=lambda item: item["score"], reverse=True)
        if scored[0]["score"] >= min_score:
            return scored[: max(1, k)]

    keywords = extract_keywords(cleaned_query)
    if not keywords:
        return []

    fallback_scored: list[dict[str, Any]] = []
    for note, text in zip(notes, texts, strict=False):
        if not text:
            continue
        score = _keyword_match_score(text, keywords)
        if score <= 0:
            continue
        fallback_scored.append(
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

    fallback_scored.sort(key=lambda item: item["score"], reverse=True)
    return fallback_scored[: max(1, k)]
