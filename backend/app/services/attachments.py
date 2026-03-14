from __future__ import annotations

from io import BytesIO
from pathlib import Path

from fastapi import HTTPException


def extract_upload_text(filename: str, content: bytes) -> tuple[str, str]:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf_text(content), "pdf"
    if suffix == ".docx":
        return _extract_docx_text(content), "docx"
    if suffix == ".txt":
        return content.decode("utf-8", errors="ignore").strip(), "txt"
    raise HTTPException(
        status_code=400,
        detail="Unsupported file type. Allowed: .pdf, .docx, .txt",
    )


def _extract_pdf_text(content: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail="PDF upload requires 'pypdf'. Install it in backend/requirements.txt.",
        ) from exc

    reader = PdfReader(BytesIO(content))
    parts: list[str] = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts).strip()


def _extract_docx_text(content: bytes) -> str:
    try:
        from docx import Document
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail="DOCX upload requires 'python-docx'. Install it in backend/requirements.txt.",
        ) from exc

    document = Document(BytesIO(content))
    return "\n".join(p.text for p in document.paragraphs).strip()
