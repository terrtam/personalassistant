"""
Health check endpoint for the API.

Provides a simple route to verify that the service is running and responsive.
"""

from fastapi import APIRouter

router = APIRouter()

@router.get("/health")
async def health():
    return {"status": "ok"}
