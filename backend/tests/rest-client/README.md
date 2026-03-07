# VS Code REST Client Tests

This folder contains API tests for the VS Code REST Client extension.

## Files

- `00-health.http`: verifies API health endpoint
- `10-llm-smoke.http`: verifies Groq connectivity
- `20-rag-flow.http`: builds embeddings index, asks answerable and unanswerable RAG questions
- `30-notes.http`: verifies creating and listing notes

## Prerequisites

1. Install extension: `humao.rest-client` in VS Code.
2. Ensure backend env is configured:
   - `backend/.env` must include `GROQ_API_KEY`.
3. Start backend:

```powershell
Set-Location "c:\Users\Terrence\Desktop\Projects\Calendar Agent\backend"
& ..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

## How to run in VS Code

1. Open any `.http` file in this folder.
2. Click `Send Request` above each request block.
3. Run in this order:
   1. `00-health.http`
   2. `10-llm-smoke.http`
   3. `20-rag-flow.http`
   4. `30-notes.http`
4. Check the response panel test output (`PASS` / `FAIL`) for each request.

## Notes

- The RAG fallback assertion allows minor wording variation from the model.
- Base URL defaults to `http://127.0.0.1:8000` in each file.
