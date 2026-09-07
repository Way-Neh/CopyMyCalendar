# Explanation: Privacy & Data Sanitization Model

This document explains the security and data privacy guarantees enforced during calendar synchronization.

---

## 1. The Principle of Minimal Exposure

Enterprise work calendars frequently contain sensitive confidential data:
- Internal project code names and strategic agendas in meeting descriptions.
- Customer emails and attendee lists.
- Zoom, Teams, or Google Meet links containing passcode tokens.
- File attachments and meeting chat links.

When syncing to an external or personal Google account, copying these fields presents significant risk of data leakage.

---

## 2. Sanitization Rules

The `MacCalendarClient` applies a strict whitelist policy during event creation and updates:

| Field | Source Event | Target Event (Gmail) | Rationale |
|---|---|---|---|
| **Title / Summary** | Preserved | Preserved | Necessary to identify the commitment on your personal schedule. |
| **Start Time** | Preserved | Preserved | Required for schedule blocking. |
| **End Time** | Preserved | Preserved | Required for schedule blocking. |
| **All-Day Flag** | Preserved | Preserved | Accurately distinguishes full-day events from timed meetings. |
| **Notes / Description** | Stripped | `""` (Empty) | Prevents confidential meeting notes from leaking. |
| **Location** | Stripped | `""` (Empty) | Avoids exposing private conference rooms or home addresses. |
| **URL / Links** | Stripped | `None` | Prevents exposing internal URLs, video passcodes, or tokens. |
| **Attendees** | Stripped | `[]` (Empty) | Prevents leaking corporate email directories. |
| **Alarms / Reminders** | Stripped | `[]` (Empty) | Prevents double-firing duplicate alerts on your devices. |

---

## 3. Local Storage Security

- **No Plaintext Content in DB**: The `sync_state.db` SQLite database stores only the ISO start/end timestamps, event identifiers, and the SHA-256 content hash. Event notes, descriptions, and attendees are never written to disk by the sync tool.
- **Audit Logs**: The `sync_events.log` records only event timestamps, titles, and diff statuses (`[CREATED]`, `[UPDATED]`, `[UNCHANGED]`, `[DELETED]`).
