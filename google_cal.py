"""
google_cal.py - Google Calendar API client for authentication, calendar management, and event syncing.
"""

import os
import datetime
from typing import Dict, Any, Optional, List

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
]


class GoogleCalendarClient:
    """Client for Google Calendar API v3."""

    def __init__(self, credentials_path: str = "credentials.json", token_path: str = "token.json"):
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.service = None
        self._authenticate()

    def _authenticate(self):
        """Authenticate using local token.json or run OAuth flow if necessary."""
        creds = None
        if os.path.exists(self.token_path):
            try:
                creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
            except Exception:
                creds = None

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception:
                    creds = None

            if not creds:
                if not os.path.exists(self.credentials_path):
                    raise FileNotFoundError(
                        f"Google OAuth credentials file '{self.credentials_path}' not found.\n"
                        "Please download your OAuth 2.0 Client Credentials JSON from Google Cloud Console "
                        f"and place it at '{self.credentials_path}'."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)

            with open(self.token_path, "w") as token:
                token.write(creds.to_json())

        self.service = build("calendar", "v3", credentials=creds)

    def get_or_create_calendar(self, calendar_name: str, time_zone: Optional[str] = None) -> str:
        """
        Find an existing Google Calendar with the given summary name,
        or create a new secondary calendar if it does not exist.
        Returns the calendarId.
        """
        # List all accessible calendars
        page_token = None
        while True:
            calendar_list = self.service.calendarList().list(pageToken=page_token).execute()
            for entry in calendar_list.get("items", []):
                if entry.get("summary") == calendar_name and not entry.get("deleted", False):
                    return entry["id"]
            page_token = calendar_list.get("nextPageToken")
            if not page_token:
                break

        # Create new secondary calendar
        tz = time_zone or "UTC"
        body = {
            "summary": calendar_name,
            "description": f"Synchronized from Mac Calendar '{calendar_name}'",
            "timeZone": tz
        }
        new_cal = self.service.calendars().insert(body=body).execute()
        return new_cal["id"]

    def _format_event_body(self, event_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Convert normalized internal event dictionary into Google Calendar resource format."""
        start_dt: datetime.datetime = event_dict["start"]
        end_dt: datetime.datetime = event_dict["end"]
        is_all_day: bool = event_dict.get("is_all_day", False)

        body: Dict[str, Any] = {
            "summary": event_dict.get("title") or "(No Title)",
            "description": event_dict.get("notes") or "",
            "location": event_dict.get("location") or "",
            "extendedProperties": {
                "private": {
                    "mac_event_id": event_dict.get("id", ""),
                    "content_hash": event_dict.get("content_hash", "")
                }
            }
        }

        # Handle URL in notes if present
        if event_dict.get("url"):
            url_str = event_dict["url"]
            if body["description"]:
                body["description"] += f"\n\nURL: {url_str}"
            else:
                body["description"] = f"URL: {url_str}"

        if is_all_day:
            # All-day dates in Google Calendar are YYYY-MM-DD strings.
            # If start == end (single day in Mac), Google Calendar end date is exclusive (start + 1 day).
            start_date_str = start_dt.strftime("%Y-%m-%d")
            end_date_str = end_dt.strftime("%Y-%m-%d")
            if start_date_str == end_date_str:
                end_dt_next = end_dt + datetime.timedelta(days=1)
                end_date_str = end_dt_next.strftime("%Y-%m-%d")
            body["start"] = {"date": start_date_str}
            body["end"] = {"date": end_date_str}
        else:
            body["start"] = {"dateTime": start_dt.isoformat()}
            body["end"] = {"dateTime": end_dt.isoformat()}

        return body

    def create_event(self, calendar_id: str, event_dict: Dict[str, Any]) -> str:
        """Create a new event in the specified Google Calendar. Returns the created gcal_event_id."""
        body = self._format_event_body(event_dict)
        created = self.service.events().insert(calendarId=calendar_id, body=body).execute()
        return created["id"]

    def update_event(self, calendar_id: str, gcal_event_id: str, event_dict: Dict[str, Any]) -> bool:
        """Update an existing event in the specified Google Calendar."""
        body = self._format_event_body(event_dict)
        try:
            self.service.events().patch(
                calendarId=calendar_id,
                eventId=gcal_event_id,
                body=body
            ).execute()
            return True
        except HttpError as e:
            if e.resp.status == 404:
                # Event was deleted on Google Calendar side, recreate it
                return False
            raise

    def delete_event(self, calendar_id: str, gcal_event_id: str) -> bool:
        """Delete an event from Google Calendar."""
        try:
            self.service.events().delete(
                calendarId=calendar_id,
                eventId=gcal_event_id
            ).execute()
            return True
        except HttpError as e:
            if e.resp.status in (404, 410):
                # Already deleted
                return True
            raise
