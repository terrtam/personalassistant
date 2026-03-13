"""
Calendar API routes.

Provides endpoints for checking Google Calendar integration,
listing events, and creating new calendar events.
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query
from googleapiclient.errors import HttpError
from pydantic import BaseModel, Field

from app.core.settings import get_settings
from app.services.calendar.google_calendar import (
    GoogleCalendarConfigError,
    create_event,
    list_events,
)

router = APIRouter(prefix="/calendar", tags=["calendar"])


class CalendarStatusResponse(BaseModel):
    enabled: bool
    calendar_id: str


class CalendarEvent(BaseModel):
    id: str | None = None
    summary: str | None = None
    description: str | None = None
    location: str | None = None
    status: str | None = None
    html_link: str | None = None
    start: dict | None = None
    end: dict | None = None


class CalendarEventsResponse(BaseModel):
    calendar_id: str
    items: list[CalendarEvent]


class CreateCalendarEventRequest(BaseModel):
    summary: str = Field(..., min_length=1, max_length=250)
    start: datetime
    end: datetime
    description: str | None = Field(default=None, max_length=8000)
    location: str | None = Field(default=None, max_length=500)


def _create_calendar_event(
    settings,
    payload: CreateCalendarEventRequest,
) -> CalendarEvent:
    for field_name, value in (("start", payload.start), ("end", payload.end)):
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise HTTPException(
                status_code=422,
                detail=f"{field_name} must include a timezone offset.",
            )
    if payload.end <= payload.start:
        raise HTTPException(
            status_code=400,
            detail="end must be later than start.",
        )

    try:
        event = create_event(
            calendar_id=settings.google_calendar_id,
            summary=payload.summary.strip(),
            start=payload.start,
            end=payload.end,
            description=payload.description.strip()
            if payload.description
            else None,
            location=payload.location.strip() if payload.location else None,
        )
    except HttpError as exc:
        status_code = getattr(exc, "status_code", None)
        if status_code is None and getattr(exc, "resp", None) is not None:
            status_code = getattr(exc.resp, "status", None)
        detail_suffix = f" (status {status_code})" if status_code else ""
        raise HTTPException(
            status_code=502,
            detail=f"Google Calendar request failed{detail_suffix}.",
        ) from exc
    except GoogleCalendarConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Google Calendar request failed: {str(exc)}",
        ) from exc
    return CalendarEvent(**event)


@router.get("/status", response_model=CalendarStatusResponse)
async def google_calendar_status() -> CalendarStatusResponse:
    settings = get_settings()
    enabled = bool(
        settings.google_client_id
        and settings.google_client_secret
        and settings.google_refresh_token
    )
    return CalendarStatusResponse(
        enabled=enabled,
        calendar_id=settings.google_calendar_id,
    )


@router.get("/events", response_model=CalendarEventsResponse)
async def get_calendar_events(
    max_results: int = Query(default=10, ge=1, le=50),
    time_min: datetime | None = Query(default=None),
    time_max: datetime | None = Query(default=None),
) -> CalendarEventsResponse:
    settings = get_settings()
    start = time_min or datetime.now(UTC)
    end = time_max

    if end and end <= start:
        raise HTTPException(
            status_code=400,
            detail="time_max must be later than time_min.",
        )
    if not end:
        end = start + timedelta(days=14)
    for field_name, value in (("time_min", start), ("time_max", end)):
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise HTTPException(
                status_code=422,
                detail=f"{field_name} must include a timezone offset.",
            )

    try:
        events = list_events(
            calendar_id=settings.google_calendar_id,
            time_min=start,
            time_max=end,
            max_results=max_results,
        )
    except HttpError as exc:
        status_code = getattr(exc, "status_code", None)
        if status_code is None and getattr(exc, "resp", None) is not None:
            status_code = getattr(exc.resp, "status", None)
        detail_suffix = f" (status {status_code})" if status_code else ""
        raise HTTPException(
            status_code=502,
            detail=f"Google Calendar request failed{detail_suffix}.",
        ) from exc
    except GoogleCalendarConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Google Calendar request failed: {str(exc)}",
        ) from exc

    return CalendarEventsResponse(
        calendar_id=settings.google_calendar_id,
        items=[CalendarEvent(**event) for event in events],
    )


@router.post("/events", response_model=CalendarEvent, status_code=201)
async def create_calendar_event(payload: CreateCalendarEventRequest) -> CalendarEvent:
    settings = get_settings()
    return _create_calendar_event(settings, payload)


@router.post("/create", response_model=CalendarEvent, status_code=201)
async def create_calendar_event_alias(
    payload: CreateCalendarEventRequest,
) -> CalendarEvent:
    settings = get_settings()
    return _create_calendar_event(settings, payload)
