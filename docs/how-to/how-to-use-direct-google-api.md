# How-To: Use Direct Google Calendar API Client

In addition to native macOS EventKit in-app syncing, the repository includes [`google_cal.py`](file:///Users/ap-wayne.tan/DockerProjects/SendtoGMAIL/google_cal.py) for direct programmatic access to the official Google Calendar REST API v3.

---

## 1. Prerequisites & Google Cloud Console Setup

1. Open the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (e.g. `Mac-Calendar-Sync`).
3. Navigate to **APIs & Services $\rightarrow$ Library**, search for **Google Calendar API**, and click **Enable**.
4. Navigate to **APIs & Services $\rightarrow$ OAuth consent screen**:
   - User Type: **External**
   - Fill in app name and developer contact email.
   - Add scope: `https://www.googleapis.com/auth/calendar`.
   - Add your Gmail address as a **Test User**.
5. Navigate to **APIs & Services $\rightarrow$ Credentials**:
   - Click **Create Credentials $\rightarrow$ OAuth client ID**.
   - Application type: **Desktop App**.
   - Click **Download JSON** and save the file in this project root as `credentials.json`.

---

## 2. Authenticating & Token Generation

The `GoogleCalendarClient` automatically launches a local web browser for OAuth 2.0 authorization on first run and caches refreshed credentials in `token.json`:

```python
from google_cal import GoogleCalendarClient

# Initializes client, runs OAuth flow if token.json is missing, or refreshes expired tokens
client = GoogleCalendarClient(
    credentials_path="credentials.json",
    token_path="token.json"
)
```

---

## 3. Basic Operations

### Find or Create a Secondary Calendar
```python
cal_id = client.get_or_create_calendar("Work Synced", time_zone="Asia/Singapore")
print(f"Target Google Calendar ID: {cal_id}")
```

### Create or Update an Event
```python
import datetime

event_data = {
    "id": "src_12345",
    "title": "Quarterly Planning",
    "start": datetime.datetime.now().astimezone(),
    "end": datetime.datetime.now().astimezone() + datetime.timedelta(hours=1),
    "is_all_day": False,
    "content_hash": "a1b2c3..."
}

# Insert new event
google_event_id = client.create_event(cal_id, event_data)

# Update existing event
event_data["title"] = "Quarterly Planning (Updated)"
client.update_event(cal_id, google_event_id, event_data)

# Delete event
client.delete_event(cal_id, google_event_id)
```
