# Reference: Python API Reference

This document describes the core Python classes and modules in the codebase.

---

## 1. `mac_calendar.py`

Provides native EventKit interactions via PyObjC.

### `class MacCalendarClient`

```python
client = MacCalendarClient()
```

#### Methods

- **`request_access() -> bool`**
  Requests user authorization to access macOS Calendar data via `EKEventStore`.

- **`get_calendars(include_event_counts: bool = False) -> List[Dict[str, Any]]`**
  Returns a list of dictionary representations of all available calendars.
  - *Returns*: `[{"title": str, "identifier": str, "source": str, "allows_modifications": bool, "event_count_1yr": int}]`.

- **`get_calendar_by_id(calendar_id: str) -> Optional[EKCalendar]`**
  Finds an `EKCalendar` instance matching `calendar_id`.

- **`get_events_by_calendar_id(calendar_id: str, start_date: datetime, end_date: datetime, chunk_days: int = 90) -> List[Dict[str, Any]]`**
  Fetches and parses all events within `[start_date, end_date]` in 90-day chunks.

- **`create_event(target_calendar_id: str, event_data: Dict[str, Any]) -> str`**
  Creates an event containing only sanitized properties (`title`, `start`, `end`, `is_all_day`) in the target calendar.
  - *Returns*: The newly assigned `eventIdentifier` string.

- **`update_event(target_event_id: str, event_data: Dict[str, Any]) -> bool`**
  Updates an existing event in the target calendar.

- **`delete_event(target_event_id: str) -> bool`**
  Deletes an event by its `eventIdentifier`.

- **`clear_calendar(calendar_id: str, start_date: Optional[datetime], end_date: Optional[datetime]) -> int`**
  Deletes all events within a calendar and commits the store.

- **`search_all_calendars(query: str, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]`**
  Performs cross-calendar event search matching `query`.

---

## 2. `sync_engine.py`

Orchestrates state persistence, hashing, diff computation, and synchronization execution.

### `class SyncStateStore`

```python
store = SyncStateStore(db_path="sync_state.db")
```

#### Methods

- **`get_all_mappings() -> Dict[str, Dict[str, Any]]`**
  Returns all mappings keyed by `source_event_id`.
- **`save_mapping(source_id: str, target_id: str, content_hash: str, start_time: str, end_time: str)`**
  Inserts or updates an event mapping record.
- **`remove_mapping(source_id: str)`**
  Removes a mapping record.
- **`clear_all_mappings()`**
  Truncates `event_mappings` and resets metadata.
- **`get_meta(key: str) -> Optional[str]`** / **`set_meta(key: str, value: str)`**
  Reads or sets metadata key-value pairs.

### `class SyncEngine`

```python
engine = SyncEngine(
    mac_client=client,
    state_store=store,
    source_calendar_id="...",
    target_calendar_id="...",
    source_calendar_name="Work",
    target_calendar_name="Gmail - Work",
    days_past=365,
    days_future=730
)
```

#### Methods

- **`compute_diff(start_date: datetime, end_date: datetime) -> Tuple[...]`**
  Calculates diff sets: `(to_create, to_update, to_delete, unchanged, all_source_events)`.
- **`sync(dry_run: bool = False, log_file: str = "sync_events.log") -> Dict[str, Any]`**
  Executes the sync operation, applies mutations, commits changes, and writes audit records.
  - *Returns*: Statistics dictionary `{"created": int, "updated": int, "deleted": int, "unchanged": int, "total_source_events": int, "dry_run": bool}`.
- **`clear_target_calendar() -> int`**
  Empties target calendar and resets state store.

---

## 3. `launchd_manager.py`

### `class LaunchdManager`

```python
manager = LaunchdManager(project_dir="...", python_path="...", interval_minutes=15)
```

#### Methods

- **`install() -> str`**: Writes LaunchAgent plist and invokes `launchctl bootstrap`.
- **`uninstall() -> bool`**: Unloads service and removes plist file.
- **`get_status() -> Dict[str, Any]`**: Checks if plist is installed and loaded into `launchctl`.

---

## 4. `outlook_calendar.py`

Interacts with Microsoft Outlook on macOS using AppleScript / `NSAppleScript`.

### `class OutlookCalendarClient`

```python
client = OutlookCalendarClient()
```

#### Methods

- **`is_outlook_running() -> bool`**
  Checks whether the Microsoft Outlook process is running.
- **`get_calendars() -> List[Dict[str, Any]]`**
  Returns list of calendars configured in Microsoft Outlook.
- **`get_events(calendar_name: str, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]`**
  Fetches and expands single and recurring occurrences within `[start_date, end_date]`.

---

## 5. `gui_app.py`

Native macOS Cocoa Menu Bar application.

### `class CalendarSyncApp`

Implements the status bar icon, preference window, vibrant visual effect views, live logs viewer, and background scheduler.

