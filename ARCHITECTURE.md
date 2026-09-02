# Technical Architecture & Internal Design

This document details the internal design, component relationships, data lifecycle, and algorithms used in the **Mac Calendar to Gmail (In-App) Sync Tool**.

---

## 1. System Architecture Diagram

```mermaid
graph TD
    subgraph macOS Environment
        EK[EventKit Framework / EKEventStore]
        CalApp[macOS Calendar App]
        LaunchD[launchd LaunchAgent]
    end

    subgraph Sync Tool Core
        CLI[sync.py CLI Entrypoint]
        MKC[mac_calendar.py - MacCalendarClient]
        SE[sync_engine.py - SyncEngine]
        SS[sync_engine.py - SyncStateStore]
        LM[launchd_manager.py - LaunchdManager]
    end

    subgraph Persistence Layer
        DB[(sync_state.db SQLite)]
        Config[config.yaml]
        Log[sync_events.log Audit Log]
    end

    LaunchD -->|Triggers at interval| CLI
    CLI -->|Loads config| Config
    CLI -->|Initializes| MKC
    CLI -->|Initializes| SS
    CLI -->|Executes| SE

    MKC <-->|PyObjC Bridge| EK
    EK <-->|Syncs Accounts| CalApp

    SE -->|Fetch Source & Target| MKC
    SE -->|Fetch Mappings & Meta| SS
    SS <-->|Read / Write| DB
    SE -->|Diff Calculation & Execution| MKC
    SE -->|Append Audit Records| Log
    CLI -->|Manage Service Plist| LM
    LM -->|Install / Unload| LaunchD
```

---

## 2. Core Modules & Responsibilities

### 2.1 `mac_calendar.py` (`MacCalendarClient`)
- **Native EventKit Interface**: Interacts with macOS's native `EKEventStore` via PyObjC bindings (`pyobjc-framework-EventKit`).
- **Calendar Resolution**: Uses strict Apple `calendarIdentifier` strings to identify calendars uniquely across accounts (Exchange, iCloud, Google, CalDAV).
- **Date Conversion**: Bridges Objective-C `NSDate` and Python `datetime.datetime` using machine local time and UNIX epoch timestamps.
- **Time Window Chunking**: To avoid memory bottlenecks or timeouts with large event datasets, event queries are executed in 90-day intervals.
- **Sanitization on Write**: When creating target events, only `title`, `startDate`, `endDate`, and `isAllDay` are copied. Fields such as `notes`, `location`, `url`, `attendees`, and `alarms` are explicitly stripped.

### 2.2 `sync_engine.py` (`SyncEngine` & `SyncStateStore`)
- **`SyncStateStore`**: A light, resilient SQLite database (`sync_state.db`) maintaining event correlation and metadata:
  ```sql
  CREATE TABLE event_mappings (
      source_event_id TEXT PRIMARY KEY,
      target_event_id TEXT NOT NULL,
      content_hash TEXT NOT NULL,
      start_time TEXT,
      end_time TEXT,
      last_synced_at TEXT NOT NULL
  );

  CREATE TABLE sync_meta (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL
  );
  ```
- **Content Hashing**: Generates a canonical SHA-256 hash of `{title, start, end, is_all_day}` to detect changes without inspecting target calendar contents.
- **Diff Computation**:
  1. Identifies source events not yet present in `event_mappings` $\rightarrow$ **Mark for creation**.
  2. Identifies mapped events whose content hash has changed or whose target event was deleted $\rightarrow$ **Mark for update / re-creation**.
  3. Identifies mappings whose source event no longer falls within the active window $\rightarrow$ **Mark for deletion**.
  4. Identifies unchanged mappings $\rightarrow$ **Preserve without I/O**.

### 2.3 `launchd_manager.py` (`LaunchdManager`)
- **macOS Service Integration**: Generates and manages the LaunchAgent property list (`com.sendtogmail.calendar-sync.plist`) under `~/Library/LaunchAgents/`.
- **Process Orchestration**: Manages `launchctl bootstrap` / `launchctl bootout` lifecycle, environment variable propagation, and standard I/O log redirects (`sync.log` and `sync.error.log`).

### 2.4 `sync.py`
- **CLI & Dispatcher**: Rich terminal UI interface providing interactive wizards, dry-run previews, bulk event dumps, search capabilities, target calendar resets, and continuous daemon execution.

---

## 3. Recurring Event Instance Expansion

In EventKit, recurring event series share a single base `eventIdentifier`. When a client requests events within a date range:
1. EventKit expands occurrences into discrete event instances.
2. The sync client generates a compound instance identifier:
   $$\text{unique\_instance\_id} = \text{base\_id} + \text{"\_"} + \text{start\_timestamp}$$
3. This allows individual instances (including modified single instances in a series) to map directly to unique target events without colliding with other occurrences in the recurring rule.

---

## 4. Error Handling & Recovery

| Failure Scenario | Mitigation |
|---|---|
| **Target Event Manually Deleted** | `SyncEngine` verifies `event_exists(target_id)`. If missing, it drops the stale mapping and re-creates the event. |
| **System Permission Revocation** | `MacCalendarClient` checks authorization prior to every query and raises a descriptive `PermissionError` with system guidance. |
| **Database Corruption / Loss** | Running `sync.py --reset-state` or `sync.py --clear-target -y` resets the local mapping cleanly. |
| **Network / Sync Delay in CalApp** | Changes made in EventKit are committed immediately to local store (`commit()`); macOS handles background synchronization upstream to Google/Exchange servers. |
