# Mac Calendar to Gmail (In-App) Sync Tool

[![macOS](https://img.shields.io/badge/macOS-12.0%2B-black?logo=apple&logoColor=white)](https://www.apple.com/macos/)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A high-performance, privacy-focused Python utility and background service that synchronizes events between calendars directly within the **macOS Calendar (EventKit)** ecosystem—typically mirroring a corporate/source calendar (e.g. Exchange, iCloud, Outlook) into a Gmail/Google calendar mapped in the macOS Calendar app.

---

## 📑 Table of Contents

- [Key Features](#-key-features)
- [How It Works & Privacy Model](#-how-it-works--privacy-model)
- [Architecture Overview](#-architecture-overview)
- [Prerequisites](#-prerequisites)
- [Installation & Setup](#-installation--setup)
- [Configuration Reference](#-configuration-reference)
- [CLI Subcommands & Usage](#-cli-subcommands--usage)
- [Automation & Background Sync](#-automation--background-sync)
  - [Method 1: Native macOS `launchd` Service (Recommended)](#method-1-native-macos-launchd-service-recommended)
  - [Method 2: Automator Workflow / Login Item](#method-2-automator-workflow--login-item)
  - [Method 3: Terminal Daemon (`nohup`)](#method-3-terminal-daemon-nohup)
- [Diagnostics & Auditing](#-diagnostics--auditing)
- [Direct Google Calendar API Integration](#-direct-google-calendar-api-integration)
- [Troubleshooting & FAQ](#-troubleshooting--faq)
- [Development & Testing](#-development--testing)

---

## ✨ Key Features

- **Direct In-App Syncing via EventKit**: Operates natively with Apple's `EventKit` framework via PyObjC—no cloud proxies, webhooks, or open incoming network ports required.
- **Privacy & Sanitization by Design**: Synchronizes only **Title**, **Start Time**, and **End Time**. Strips meeting notes, descriptions, attendee lists, video conference links, attachments, and personal alarms to prevent accidental data leaks to external calendars.
- **Unique Calendar Identifier Matching**: Anchors calendars to macOS `calendarIdentifier` strings, preventing ambiguity if multiple calendars share the same title across different accounts.
- **Intelligent Diff & Content Hashing**: Uses SHA-256 fingerprinting on event instances to execute only necessary creates, updates, and deletes, minimizing I/O and preventing duplicate entries.
- **Full Recurrence Support**: Automatically evaluates and expands recurring rules into concrete time-chunked instances (`<event_id>_<start_timestamp>`) across custom time windows.
- **Automated Background Daemons**: Out-of-the-box integration for macOS `launchd` LaunchAgents, Automator workflows, or continuous daemon loops.
- **Comprehensive Audit Trails**: Maintains SQLite sync state (`sync_state.db`) and human-readable line-by-line event audit logs (`sync_events.log`).

---

## 🔒 How It Works & Privacy Model

When syncing corporate calendars (e.g., Microsoft 365, Exchange) with personal Google accounts, privacy and data leak prevention are essential. 

```
┌───────────────────────────────────────────────────────────┐
│                     macOS Calendar                        │
│                                                           │
│  [Source Calendar]                 [Target Calendar]      │
│  (Exchange / iCloud / Work)        (Google / Gmail Account)│
│          │                                  ▲             │
└──────────┼──────────────────────────────────┼─────────────┘
           │                                  │
    (1) Read Events                    (4) Write / Update
           ▼                                  │
┌───────────────────────────────────────────────────────────┐
│               Local Sync Engine (Python)                  │
│                                                           │
│  • Strip Notes, URLs, Attendees, Alarms                   │
│  • Compute SHA-256 Instance Fingerprint                   │
│  • Compare with SQLite State Store (sync_state.db)        │
│  • Determine diff: [Create / Update / Delete / Keep]      │
└───────────────────────────────────────────────────────────┘
```

1. **Source Event Extraction**: Queries Apple's `EKEventStore` for events within your configured rolling window (e.g., past 365 days to future 730 days).
2. **Sanitization**: Preserves only event start/end datetime, all-day status, and title. All sensitive metadata (attendee emails, attachments, notes, locations, conference links) is discarded.
3. **Fingerprinting & Diffing**: Checks local `sync_state.db` SQLite store:
   - **New Event**: Creates a clean event in the target calendar and records the identifier mapping.
   - **Updated Event**: Modifies time or title if the SHA-256 payload hash changed.
   - **Deleted Event**: Removes orphaned target events if the source event was removed within the window.
4. **Target Synchronization**: Writes modifications back to EventKit in the macOS Calendar app, which macOS silently synchronizes upstream to Google Calendar.

---

## 🏗️ Architecture Overview

```
.
├── CalendarSync.workflow       # macOS Automator workflow for login execution
├── config.yaml                 # Active configuration (generated via setup)
├── config.yaml.example         # Example configuration template
├── google_cal.py               # Optional direct Google Calendar REST API v3 client
├── launchd_manager.py          # macOS LaunchAgent (.plist) manager
├── mac_calendar.py             # EventKit bridge (PyObjC) for macOS Calendar store
├── requirements.txt            # Python package dependencies
├── run_sync.sh                 # Shell wrapper for launchd / cron / automator
├── sync.py                     # Main CLI controller and entrypoint
├── sync_engine.py              # Core diff algorithm, hashing, and SQLite state store
├── sync_state.db               # SQLite database mapping source <-> target IDs
├── sync_events.log             # Formatted sync audit trail
└── test_sync_engine.py         # Unit test suite
```

---

## 📋 Prerequisites

1. **macOS 12.0 (Monterey)** or later.
2. **Python 3.9+** (installed via Homebrew or Xcode Command Line Tools).
3. **macOS Calendar Permissions**:
   - Terminal or IDE must have permissions to access macOS Calendars.
   - Go to **System Settings $\rightarrow$ Privacy & Security $\rightarrow$ Calendars** and ensure your terminal emulator (e.g. `Terminal`, `iTerm2`, `Alacritty`, `VS Code`) is allowed.
4. Both **Source Calendar** (e.g., Exchange/Work) and **Target Calendar** (e.g., Google/Gmail) must be added and visible in the macOS Calendar app (**Calendar $\rightarrow$ Settings $\rightarrow$ Accounts**).

---

## 🚀 Installation & Setup

### 1. Clone the repository & enter the directory

```bash
git clone <repository_url> SendtoGMAIL
cd SendtoGMAIL
```

### 2. Create and activate a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the interactive setup wizard

```bash
python3 sync.py setup
```

The wizard will:
1. Query macOS Calendar and display all accounts and calendars with event counts.
2. Prompt you to choose your **Source** calendar.
3. Prompt you to choose your **Target (Gmail)** calendar.
4. Configure your rolling time window and background sync intervals.
5. Save the unique identifiers to `config.yaml`.

---

## ⚙️ Configuration Reference

The configuration file is saved as `config.yaml` in the project root:

```yaml
# Unique Calendar Identifiers (retrieved via 'python3 sync.py list-calendars')
source_calendar_id: "D16938BC-9D12-4043-98C1-8C5DCB10629E"
source_calendar_name: "Work"
source_calendar_account: "Exchange"

target_calendar_id: "8E04C741-94E5-46D2-B83F-31644A159D71"
target_calendar_name: "Gmail - Work"
target_calendar_account: "Google"

# Time window for active sync (in days)
rolling_days_past: 365       # Days in the past to monitor
rolling_days_future: 730     # Days in the future to monitor

# Background sync frequency (for launchd service)
sync_interval_minutes: 15

# Local SQLite mapping database
state_db_file: "sync_state.db"
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `source_calendar_id` | String | - | macOS `calendarIdentifier` for the source calendar |
| `source_calendar_name` | String | `"Work"` | Human-readable name for logging |
| `target_calendar_id` | String | - | macOS `calendarIdentifier` for the target calendar |
| `target_calendar_name` | String | `"Gmail - Work"` | Human-readable target name |
| `rolling_days_past` | Integer | `365` | Number of days before today to sync |
| `rolling_days_future` | Integer | `730` | Number of days ahead of today to sync |
| `sync_interval_minutes` | Integer | `15` | Polling interval for automated sync |
| `state_db_file` | String | `"sync_state.db"` | Path to SQLite mapping database |

---

## 💻 CLI Subcommands & Usage

You can invoke `sync.py` using positional subcommands or flag-based commands.

### 1. List Calendars
Displays all available calendars on your Mac with source accounts, event counts (±1 year), and unique IDs.
```bash
python3 sync.py list-calendars
```

### 2. Run a Synchronization Pass
Runs a single synchronization cycle based on `config.yaml`.
```bash
# Standard sync (using configured rolling window)
python3 sync.py sync

# Sync entire history (10 years past & future)
python3 sync.py sync --all-time

# Preview changes without modifying target calendar
python3 sync.py sync --dry-run

# Override time window on the fly
python3 sync.py sync --days-past 60 --days-future 90
```

### 3. Clear Target Calendar
Completely empties all events in the target calendar and clears the SQLite state store. Useful when resetting or re-indexing.
```bash
# Interactive confirmation prompt
python3 sync.py clear-target

# Force deletion without prompt
python3 sync.py clear-target -y
```

### 4. Search Events Across All Mac Calendars
Quickly search all calendars on your machine for a specific event title to troubleshoot or find missing items.
```bash
python3 sync.py find "Sprint Planning"
```

### 5. Dump Source Events to File
Exports all source calendar events formatted with machine local time to `events_dump.txt`.
```bash
python3 sync.py dump-events --all-time
```

### 6. View Live Audit Log
Prints the most recent line-by-line sync execution logs.
```bash
python3 sync.py log -n 50
```

### 7. Reset State Database
Removes `sync_state.db` so the next sync run executes a clean scan and re-associates events.
```bash
python3 sync.py reset-state
```

### 8. Check Status
Displays calendar configurations, SQLite state info, and macOS LaunchAgent service status.
```bash
python3 sync.py status
```

---

## ⏱️ Automation & Background Sync

Choose one of three methods to run synchronization automatically in the background:

### Method 1: Native macOS `launchd` Service (Recommended)

The tool provides built-in management for native macOS LaunchAgents (`~/Library/LaunchAgents/com.sendtogmail.calendar-sync.plist`). This runs automatically on boot/login, wakes with the system, and executes at the configured interval.

```bash
# 1. Install and load the LaunchAgent
python3 sync.py install-service

# 2. Check service status
python3 sync.py status

# 3. View service logs
tail -f sync.log
tail -f sync.error.log

# 4. Uninstall / Unload the service
python3 sync.py uninstall-service
```

### Method 2: Automator Workflow / Login Item

Use the included [`CalendarSync.workflow`](file:///Users/ap-wayne.tan/DockerProjects/SendtoGMAIL/CalendarSync.workflow) for zero-terminal UI integration:

1. Double-click `CalendarSync.workflow` to open it in **Automator**.
2. Go to **File $\rightarrow$ Export...** and save it as an **Application** (e.g. `CalendarSync.app`).
3. Open **System Settings $\rightarrow$ General $\rightarrow$ Login Items**.
4. Click **+** and add `CalendarSync.app`.
5. The sync engine will now run silently every time you log in to macOS.

### Method 3: Terminal Daemon (`nohup`)

To run a persistent loop directly in your terminal session:

```bash
# Start daemon in background (runs every 15 minutes)
nohup python3 sync.py daemon --interval 15 > daemon.log 2>&1 &

# Monitor output
tail -f daemon.log

# Stop the daemon
pkill -f "sync.py daemon"
```

---

## 🔍 Diagnostics & Auditing

### Audit Log (`sync_events.log`)
Every sync run logs its exact diff decisions:
```text
================================================================================
SYNC RUN (Machine Time): 2026-09-03 01:30:00 +08
SOURCE CALENDAR : 'Work' [ID: D16938BC-9D12-4043-98C1-8C5DCB10629E]
TARGET CALENDAR : 'Gmail - Work' [ID: 8E04C741-94E5-46D2-B83F-31644A159D71]
WINDOW          : 2025-09-03 01:30 to 2028-09-03 01:30 (365d past, 730d future)
TOTAL DETECTED  : 142 source events found
PLAN            : 2 to create | 1 to update | 0 to delete | 139 unchanged
MODE            : REAL SYNC
--------------------------------------------------------------------------------
STATUS       | LOCAL MACHINE TIME     | EVENT TITLE
--------------------------------------------------------------------------------
[CREATED]    | 2026-09-04 10:00       | Architecture Review
[UPDATED]    | 2026-09-05 14:30       | Team Standup (Rescheduled)
[UNCHANGED]  | 2026-09-06 09:00       | 1:1 Sync
================================================================================
```

---

## 🌐 Direct Google Calendar API Integration

In addition to in-app EventKit syncing, the project includes [`google_cal.py`](file:///Users/ap-wayne.tan/DockerProjects/SendtoGMAIL/google_cal.py) for direct API interactions with Google Calendar v3 REST API.

### Setup Google Cloud OAuth (Optional)
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a project and enable the **Google Calendar API**.
3. Configure an OAuth Consent Screen and create an **OAuth 2.0 Client ID (Desktop App)**.
4. Download the client secret JSON and save it as `credentials.json` in the project root.
5. `GoogleCalendarClient` handles initial browser-based authentication and caches tokens in `token.json`.

---

## 🛠️ Troubleshooting & FAQ

### Q: EventKit Permission Denied Error (`PermissionError: Calendar access was denied`)
**Fix**:
1. Open **System Settings $\rightarrow$ Privacy & Security $\rightarrow$ Calendars**.
2. Enable access for your terminal (Terminal, iTerm2, VS Code, etc.).
3. If running via `launchd`, ensure `zsh` or the parent shell has calendar permissions.
4. You can reset calendar permissions with:
   ```bash
   tccutil reset Calendar
   ```

### Q: Duplicate events appearing in target calendar
**Cause**: Usually occurs if the calendar was partially synced before using unique calendar IDs, or if events were created manually in the target calendar.
**Fix**:
```bash
# 1. Clear target calendar and reset SQLite mapping
python3 sync.py clear-target -y

# 2. Perform a fresh all-time sync
python3 sync.py sync --all-time
```

### Q: Timezone offsets or shifted event times
**Fix**: All EventKit operations automatically convert timestamps to your Mac's current machine local timezone (`datetime.astimezone()`). Ensure your Mac's system time and timezone are set accurately in **System Settings $\rightarrow$ General $\rightarrow$ Date & Time**.

---

## 🧪 Development & Testing

Unit tests run with Python's standard `unittest` framework and verify state store transactions, content hashing, and diff calculation logic:

```bash
python3 test_sync_engine.py
```

### Code Formatting & Quality
```bash
python3 -m unittest discover -v
```

---

## 📄 License

This project is licensed under the MIT License.
