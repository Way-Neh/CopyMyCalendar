# How to Sync Directly from Microsoft Outlook for Mac

This guide explains how to synchronize events directly from the Microsoft Outlook macOS desktop application via `outlook_calendar.py`.

---

## 1. When to Use Direct Outlook Sync

If your corporate Exchange account cannot be added to macOS Calendar (due to company Mobile Device Management / Intune restrictions or lack of CalDAV/Exchange support in Apple Calendar), you can read events directly from the running Microsoft Outlook desktop app.

---

## 2. Prerequisites & Automation Permissions

macOS requires Apple Events automation permissions for Python/CalendarSync to communicate with Microsoft Outlook.

1. Launch **Microsoft Outlook** on macOS and ensure your work profile is logged in.
2. When prompted by macOS, allow **CalendarSync** (or Terminal / Python) to control Microsoft Outlook.
3. If permissions were previously denied (error `-1743`):
   - Open **System Settings** $\rightarrow$ **Privacy & Security** $\rightarrow$ **Automation**.
   - Expand **Terminal** / **Python** / **CalendarSync.app**.
   - Ensure the toggle for **Microsoft Outlook** is set to **ON**.

---

## 3. Verifying Outlook Connectivity

Run the Outlook calendar test suite or interactive inspect command:

```bash
source venv/bin/activate

# Run automated tests
python3 test_outlook_calendar.py

# Inspect Outlook events directly from CLI
python3 sync.py inspect
```

---

## 4. How Recurrence and Timezones are Handled

- **Instance Expansion**: `outlook_calendar.py` parses Outlook recurrence patterns (daily, weekly, monthly, nth-weekday) and expands them into discrete occurrences over the configured rolling window using `dateutil.rrule`.
- **Timezone Normalization**: All event timestamps are mapped to macOS local machine time (`tz.tzlocal()`) to prevent UTC offset shifts.
- **Privacy Stripping**: Meeting bodies, attendee emails, and video conferencing links are stripped prior to mapping.
