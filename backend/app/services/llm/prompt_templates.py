from typing import Any


INTENT_PROMPT_TEMPLATE = """You are an intent classifier for a calendar, notes, and knowledge-base assistant.

Extract the user's intent and any relevant details.

Fields:
- title: event title or note title when applicable
- content: note content for create_note or update_note
- date: ISO date for calendar intents
- time: HH:MM for calendar intents

Possible intents:
- create_event
- query_calendar
- update_event
- delete_event
- create_note
- query_notes
- update_note
- delete_note
- rag_query
- needs_clarification
- chat

Use rag_query for questions about uploaded documents, PDFs, or stored knowledge.

Return ONLY valid JSON."""

CHAT_PROMPT_TEMPLATE = """You are a helpful assistant for a single-user calendar and notes app.
Respond conversationally and keep replies concise.
If the user asks about calendar actions, answer conversationally without claiming you completed actions.

User message:
{message}
"""


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
