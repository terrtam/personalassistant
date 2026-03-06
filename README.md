# AI Personal Assistant (Calendar + Notes + RAG)

## Overview

AI Personal Assistant is a single-user full-stack web application that integrates:

- Google Calendar (OAuth + event management)
- Personal notes storage
- PDF document ingestion
- Retrieval-Augmented Generation (RAG)
- Voice input (browser-based)
- Context-aware AI chat

The system demonstrates end-to-end LLM integration with real-world APIs and vector-based semantic retrieval.

---

## Architecture

High-level flow:

Client (React)
    ↓
FastAPI Backend
    ↓
-----------------------------------------
| Google Calendar API                  |
| Vector Database (FAISS)              |
| LLM Provider (Groq via LangChain)    |
-----------------------------------------

### RAG Pipeline

1. User submits query
2. Query embedding generated
3. Top-k relevant chunks retrieved from vector DB
4. Retrieved context injected into LLM prompt
5. LLM generates grounded response
6. Response returned to client

---

## Tech Stack

### Frontend
- React
- Axios
- Tailwind CSS

### Backend
- Python 3.10+
- FastAPI
- SQLAlchemy (optional)
- Pydantic

### AI / Retrieval
- LangChain
- Groq LLM API
- FAISS (local vector database)
- Embedding model (OpenAI-compatible or local)

### External APIs
- Google Calendar API (OAuth 2.0)

---

## Core Features

### 1. Google Calendar Integration

- OAuth 2.0 authentication
- Fetch upcoming events
- Create, update, delete events
- Leverages Google-native reminders (no custom scheduler)

### 2. Notes System

- CRUD operations for notes
- Notes stored in relational database
- Notes embedded and stored in FAISS
- Semantic retrieval via RAG

### 3. PDF Knowledge Base

- Upload PDFs
- Text extraction
- Chunking strategy
- Embedding generation
- Stored in FAISS
- Queryable via AI chat

### 4. AI Chat (RAG-Enhanced)

- Context-aware answers
- Retrieves relevant notes + document chunks
- Injects retrieved context into prompt template
- Uses Groq-hosted LLM

### 5. Voice Input

- Browser Web Speech API
- Speech → text
- Used for:
  - Note creation
  - Event scheduling
  - Chat queries

---

## Design Decisions

- Single-user architecture
- No registration system
- User configured in backend environment
- Multiple browser tabs supported
- Stateless REST API
- Local vector DB (FAISS) for simplicity
- Short sprint-based development (2-week MVP scope)

---

## Project Structure (Suggested)

backend/
    app/
        main.py
        routes/
        services/
        models/
        rag/
        auth/
    requirements.txt

frontend/
    src/
        components/
        pages/
        services/
    package.json

---

## Environment Variables

Backend requires:

GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GROQ_API_KEY=
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_TEMPERATURE=0.2
GROQ_TIMEOUT_SECONDS=30
DATABASE_URL=
CORS_ORIGIN_IP=127.0.0.1
CORS_ORIGIN_SCHEME=http
CORS_ORIGIN_PORTS=3000,5173

---

## Local Setup

### Backend

1. Create virtual environment
2. Install dependencies:
   pip install -r requirements.txt
3. Configure environment variables
4. Run locally (localhost only):
   uvicorn app.main:app --reload
5. Run for access from your known LAN IP (same network):
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   Then open `http://<your-known-ip>:8000` (example: `http://192.168.1.50:8000`).

### Frontend

1. Install dependencies:
   npm install
2. Start dev server:
   npm run dev

---

## Example Use Cases

Create event:
"Schedule meeting tomorrow at 3pm"

Query schedule:
"What do I have this week?"

Query document:
"What does the uploaded PDF say about embeddings?"

Create note:
"Reminder to follow up on internship application"

---

## Non-Functional Requirements

- Response latency target: <3 seconds for RAG queries
- OAuth-secured API access
- Async endpoints for I/O operations
- Clean separation of concerns (routes, services, retrieval logic)

---

## Limitations

- Single-user only
- Local FAISS index (not distributed)
- No production deployment included
- Basic prompt engineering

---

## Future Improvements

- Multi-user authentication
- Hosted vector database
- Dockerization
- Cloud deployment
- Advanced natural language event parsing
- Improved prompt optimization
- Persistent memory beyond notes/PDFs

---

## Purpose

This project demonstrates:

- Practical RAG implementation
- LLM orchestration using LangChain
- External API integration (Google OAuth + Calendar)
- Vector search and embedding workflows
- Full-stack system design

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


