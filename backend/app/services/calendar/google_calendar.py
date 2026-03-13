"""
Google Calendar service utilities.

Handles authentication and provides helper functions for interacting
with the Google Calendar API, including listing, creating, updating,
and deleting calendar events.
"""

from __future__ import annotations

from datetime import datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import Resource, build

from app.core.settings import get_settings

CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar"]


class GoogleCalendarConfigError(ValueError):
    """Raised when required Google Calendar settings are missing."""


def _require(value: str | None, env_name: str) -> str:
    if not value or not value.strip():
        raise GoogleCalendarConfigError(
            f"{env_name} is required to enable Google Calendar API."
        )
    return value.strip()


def build_google_credentials() -> Credentials:
    settings = get_settings()
    client_id = _require(settings.google_client_id, "GOOGLE_CLIENT_ID")
    client_secret = _require(settings.google_client_secret, "GOOGLE_CLIENT_SECRET")
    refresh_token = _require(settings.google_refresh_token, "GOOGLE_REFRESH_TOKEN")

    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=settings.google_token_uri,
        client_id=client_id,
        client_secret=client_secret,
        scopes=CALENDAR_SCOPES,
    )
    credentials.refresh(Request())
    return credentials


def get_calendar_service() -> Resource:
    credentials = build_google_credentials()
    return build("calendar", "v3", credentials=credentials, cache_discovery=False)


def list_events(
    *,
    calendar_id: str,
    time_min: datetime,
    time_max: datetime | None = None,
    max_results: int = 10,
) -> list[dict]:
    service = get_calendar_service()
    response = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=time_min.isoformat(),
            timeMax=time_max.isoformat() if time_max else None,
            singleEvents=True,
            orderBy="startTime",
            maxResults=max_results,
        )
        .execute()
    )
    return list(response.get("items", []))


def create_event(
    *,
    calendar_id: str,
    summary: str,
    start: datetime,
    end: datetime,
    description: str | None = None,
    location: str | None = None,
) -> dict:
    service = get_calendar_service()
    body = {
        "summary": summary,
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": end.isoformat()},
    }
    if description:
        body["description"] = description
    if location:
        body["location"] = location

    return (
        service.events()
        .insert(calendarId=calendar_id, body=body)
        .execute()
    )


def update_event(
    *,
    calendar_id: str,
    event_id: str,
    summary: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    description: str | None = None,
    location: str | None = None,
) -> dict:
    service = get_calendar_service()
    body: dict[str, object] = {}
    if summary is not None:
        body["summary"] = summary
    if start is not None:
        body["start"] = {"dateTime": start.isoformat()}
    if end is not None:
        body["end"] = {"dateTime": end.isoformat()}
    if description is not None:
        body["description"] = description
    if location is not None:
        body["location"] = location

    return (
        service.events()
        .patch(calendarId=calendar_id, eventId=event_id, body=body)
        .execute()
    )


def delete_event(*, calendar_id: str, event_id: str) -> None:
    service = get_calendar_service()
    service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
