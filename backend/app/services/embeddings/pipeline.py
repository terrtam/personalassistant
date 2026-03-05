from pathlib import Path
from typing import Any

from langchain_chroma import Chroma
from langchain_core.documents import Document

from app.core.settings import get_settings
from app.services.embeddings.embedding_client import get_embedding_model


def _split_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if chunk_overlap >= chunk_size:
        chunk_overlap = max(0, chunk_size // 4)

    chunks: list[str] = []
    start = 0
    text_len = len(text)
    step = max(1, chunk_size - chunk_overlap)
    while start < text_len:
        end = min(text_len, start + chunk_size)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= text_len:
            break
        start += step
    return chunks


def build_index(
    documents: list[dict[str, Any]],
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> dict[str, int]:
    settings = get_settings()
    resolved_chunk_size = chunk_size or settings.embedding_chunk_size
    resolved_chunk_overlap = chunk_overlap or settings.embedding_chunk_overlap

    split_docs: list[Document] = []
    source_count = 0
    for item in documents:
        text = (item.get("text") or "").strip()
        if not text:
            continue
        source_count += 1
        metadata = dict(item.get("metadata") or {})
        if item.get("id"):
            metadata["source_id"] = str(item["id"])
        for idx, chunk in enumerate(
            _split_text(
                text=text,
                chunk_size=resolved_chunk_size,
                chunk_overlap=resolved_chunk_overlap,
            )
        ):
            chunk_metadata = dict(metadata)
            chunk_metadata["chunk_index"] = idx
            split_docs.append(Document(page_content=chunk, metadata=chunk_metadata))
    if not split_docs:
        raise ValueError("No documents with text were provided for indexing.")

    index_path = Path(settings.embedding_index_path)
    index_path.mkdir(parents=True, exist_ok=True)
    embeddings = get_embedding_model()
    Chroma.from_documents(
        documents=split_docs,
        embedding=embeddings,
        persist_directory=str(index_path),
        collection_name="calendar_agent",
    )

    return {
        "source_documents": source_count,
        "chunks": len(split_docs),
    }


def search_index(query: str, k: int = 5) -> list[dict[str, Any]]:
    settings = get_settings()
    index_path = Path(settings.embedding_index_path)
    if not index_path.exists():
        raise FileNotFoundError(
            "No embedding index found. Build index first at "
            f"{settings.embedding_index_path}."
        )

    embeddings = get_embedding_model()
    vector_store = Chroma(
        embedding_function=embeddings,
        persist_directory=str(index_path),
        collection_name="calendar_agent",
    )
    docs_with_score = vector_store.similarity_search_with_score(query, k=k)

    results: list[dict[str, Any]] = []
    for doc, score in docs_with_score:
        results.append(
            {
                "text": doc.page_content,
                "metadata": doc.metadata,
                "score": float(score),
            }
        )
    return results
