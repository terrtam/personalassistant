from typing import Any


RAG_PROMPT_TEMPLATE = """You are a retrieval-grounded assistant for Calendar Agent.

Follow these rules exactly:
1. Use only information from the SOURCES section.
2. If the sources do not contain enough information, say: "I don't have enough context in the retrieved sources to answer that fully."
3. Do not invent facts, names, dates, links, or actions.
4. When stating facts, cite sources inline using [Source N].
5. If sources conflict, explicitly note the conflict and cite each conflicting source.
6. Keep the final answer concise and practical.

Question:
{question}

SOURCES:
{context}

Response format:
Answer: <direct answer with citations>
Evidence:
- <supporting point with citation>
- <supporting point with citation>
"""


def _format_source_metadata(metadata: dict[str, Any]) -> str:
    if not metadata:
        return "none"
    allowed_keys = ["source", "file_name", "title", "path", "page", "chunk"]
    metadata_parts = [
        f"{key}={metadata[key]}"
        for key in allowed_keys
        if key in metadata and metadata[key] not in (None, "")
    ]
    return ", ".join(metadata_parts) if metadata_parts else "none"


def build_rag_prompt(question: str, sources: list[dict[str, Any]]) -> str:
    context_blocks: list[str] = []
    for idx, source in enumerate(sources, start=1):
        text = str(source.get("text", "")).strip()
        metadata = source.get("metadata", {})
        context_blocks.append(
            f"[Source {idx}]\n"
            f"Text: {text}\n"
            f"Metadata: {_format_source_metadata(metadata)}"
        )

    context = "\n\n".join(context_blocks)
    return RAG_PROMPT_TEMPLATE.format(question=question.strip(), context=context)
