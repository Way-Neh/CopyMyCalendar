# Reference: SQLite State Database Schema

The local SQLite store (`sync_state.db`) records event mappings between source and target calendars.

---

## Tables

### 1. `event_mappings`

Stores 1-to-1 mappings between source event instance IDs and corresponding target event IDs.

```sql
CREATE TABLE IF NOT EXISTS event_mappings (
    source_event_id TEXT PRIMARY KEY,
    target_event_id TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    start_time TEXT,
    end_time TEXT,
    last_synced_at TEXT NOT NULL
);
```

#### Column Details

| Column | Type | Description |
|---|---|---|
| `source_event_id` | `TEXT` (Primary Key) | Compound event instance ID: `<base_event_id>_<start_unix_timestamp>`. |
| `target_event_id` | `TEXT` | Native `EKEvent.eventIdentifier` created in the target calendar. |
| `content_hash` | `TEXT` | Hex-encoded SHA-256 digest of `{title, start, end, is_all_day}`. |
| `start_time` | `TEXT` | ISO 8601 representation of start time with timezone offset. |
| `end_time` | `TEXT` | ISO 8601 representation of end time with timezone offset. |
| `last_synced_at` | `TEXT` | ISO 8601 timestamp when this record was written or updated. |

---

### 2. `sync_meta`

Stores key-value execution metadata.

```sql
CREATE TABLE IF NOT EXISTS sync_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

#### Common Keys

| Key | Example Value | Description |
|---|---|---|
| `last_sync_time` | `"2026-09-03T01:30:00+08:00"` | Timestamp of the most recent sync completion. |
| `source_calendar_id` | `"D16938BC-9D12-4043-98C1-8C5DCB10629E"` | Source calendar identifier used during last sync. |
| `target_calendar_id` | `"8E04C741-94E5-46D2-B83F-31644A159D71"` | Target calendar identifier used during last sync. |
