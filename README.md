# AI Personal Assistant (Calendar + Notes + RAG)

## Overview

AI Personal Assistant is a single-user full-stack web application that integrates:

- Google Calendar (single configured user; no end-user OAuth flow)
- Personal notes storage (SQLite / simple local storage)
- Document ingestion for retrieval
- Retrieval-Augmented Generation (RAG)
- Voice input (browser-based)
- Context-aware AI chat

The system demonstrates end-to-end LLM integration with practical retrieval over local knowledge sources.

---

## Architecture

High-level flow:

Client (React)
    ?
FastAPI Backend
    ?
------------------------------------------
| Google Calendar API (configured user)  |
| Vector Database (Chroma)               |
| LLM Provider (Groq)                    |
------------------------------------------

### RAG Pipeline

1. User submits query
2. Query embedding generated
3. Top-k relevant chunks retrieved from Chroma
4. Retrieved context injected into LLM prompt
5. LLM generates grounded response
6. Response returned to client

---

## Tech Stack

### Frontend
- React
- Vite
- Tailwind CSS

### Backend
- Python 3.10+
- FastAPI
- Pydantic

### AI / Retrieval
- LangChain ecosystem
- Groq LLM API
- Chroma (local persistent vector database)
- Embedding model (hash, HuggingFace, or OpenAI)

### External APIs
- Google Calendar API (single configured account)

---

## Core Features

### 1. Google Calendar Integration

- Single-user calendar integration
- No in-app end-user OAuth authentication flow
- Backend uses configured credentials/user context
- Fetch and action calendar data for the configured user

### 2. Notes System

- CRUD operations for notes
- Notes stored in SQLite / simple local persistence
- Notes can be indexed for semantic retrieval

### 3. Document Knowledge Base

- Upload `.pdf`, `.docx`, or `.txt`
- Text extraction + chunking
- Embedding generation
- Indexed in Chroma
- Queryable via AI chat

### 4. AI Chat (RAG-Enhanced)

- Context-aware answers using retrieved sources
- Chat API is stateless
- Main chat interface is `POST /ask`
- Conversation history is frontend-only (UI state)

### 5. Voice Input

- Browser Web Speech API
- Speech ? text for prompt composition

---

## Design Decisions

- Single-user architecture
- No registration system
- User configured in backend environment
- Stateless REST chat interface
- Chat memory kept on frontend only
- Local Chroma vector DB for simplicity

---

## Project Structure (Suggested)

backend/
    app/
        main.py
        routes/
        services/
        core/
    requirements.txt

frontend/
    src/
        components/
        lib/
    package.json

---

## Environment Variables

Backend requires:

GROQ_API_KEY=
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_TEMPERATURE=0.2
GROQ_TIMEOUT_SECONDS=30
EMBEDDING_PROVIDER=hash
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_INDEX_PATH=./data/chroma_db
EMBEDDING_CHUNK_SIZE=800
EMBEDDING_CHUNK_OVERLAP=120
OPENAI_API_KEY=
CORS_ORIGIN_IP=127.0.0.1
CORS_ORIGIN_SCHEME=http
CORS_ORIGIN_PORTS=3000,5173

---

## Local Setup

### Backend

1. Create virtual environment
2. Install dependencies:
   pip install -r backend/requirements.txt
3. Configure environment variables in `backend/.env`
4. Run locally:
   uvicorn app.main:app --reload --app-dir backend

### Frontend

1. Install dependencies:
   cd frontend && pnpm install
2. Start dev server:
   pnpm dev
3. Optional API base URL:
   VITE_API_BASE_URL=http://127.0.0.1:8000

---

## Example Use Cases

Calendar question:
"What do I have this week?"

Query indexed documents:
"What does our policy doc say about standup timing?"

Create note:
"Reminder to follow up on internship application"

---

## Non-Functional Requirements

- Stateless backend chat endpoint
- Async-friendly API design
- Retrieval-grounded responses with source citations
- Clean separation of concerns (routes, services, retrieval logic)

---

## Limitations

- Single-user only
- Local vector index (not distributed)
- No multi-tenant authentication model
- Chat history is not persisted server-side

---

## Future Improvements

- Multi-user support
- Hosted vector database
- Dockerization
- Cloud deployment
- Better calendar intent parsing
- Improved prompt optimization

---

## Purpose

This project demonstrates:

- Practical RAG implementation with Chroma
- LLM orchestration with Groq
- Calendar + notes + document retrieval workflows
- Full-stack architecture with stateless chat API

---

## Groq Setup (Implemented)

### Additional Backend Environment Variables

Add these in `backend/.env`:

GROQ_API_KEY=
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_TEMPERATURE=0.2
GROQ_TIMEOUT_SECONDS=30
CORS_ORIGIN_IP=127.0.0.1
CORS_ORIGIN_SCHEME=http
CORS_ORIGIN_PORTS=3000,5173

### Groq Smoke Test Endpoint

`POST /api/llm/smoke`

Request body:

```json
{
  "prompt": "Reply with: Groq connected"
}
```

Example curl:

```bash
curl -X POST "http://127.0.0.1:8000/api/llm/smoke" \
  -H "Content-Type: application/json" \
  -d "{\"prompt\":\"Reply with: Groq connected\"}"
```
