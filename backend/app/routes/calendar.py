from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query
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

    try:
        events = list_events(
            calendar_id=settings.google_calendar_id,
            time_min=start,
            time_max=end,
            max_results=max_results,
        )
    except GoogleCalendarConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
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
    except GoogleCalendarConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Google Calendar request failed: {str(exc)}",
        ) from exc
    return CalendarEvent(**event)
