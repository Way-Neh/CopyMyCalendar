# Reference: Configuration File (`config.yaml`)

Configuration is stored in YAML format in `config.yaml` at the project root.

---

## Schema & Parameters

```yaml
# Source Calendar Settings
source_calendar_id: "D16938BC-9D12-4043-98C1-8C5DCB10629E"
source_calendar_name: "Work"
source_calendar_account: "Exchange"

# Target Calendar Settings (Gmail)
target_calendar_id: "8E04C741-94E5-46D2-B83F-31644A159D71"
target_calendar_name: "Gmail - Work"
target_calendar_account: "Google"

# Synchronization Window
rolling_days_past: 365
rolling_days_future: 730

# Background Daemon Execution
sync_interval_minutes: 15

# State Storage
state_db_file: "sync_state.db"
```

---

## Parameter Descriptions

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `source_calendar_id` | String | **Yes** | - | Unique identifier for the source calendar. Supports macOS EventKit UUIDs (e.g. `0151F250-...`) or Microsoft Outlook IDs prefixed with `outlook:` (e.g. `outlook:141`). |
| `source_calendar_name` | String | No | `"Work"` | Informative name displayed in logs and summaries. |
| `source_calendar_account` | String | No | `"Local"` | Account / Provider name (e.g. Exchange, iCloud). |
| `target_calendar_id` | String | **Yes** | - | The unique macOS `calendarIdentifier` for the target Gmail calendar. |
| `target_calendar_name` | String | No | `"Gmail - Work"` | Informative target name displayed in logs. |
| `target_calendar_account` | String | No | `"Google"` | Target account name. |
| `rolling_days_past` | Integer | No | `365` | Number of days prior to current date to include in active sync window. |
| `rolling_days_future` | Integer | No | `730` | Number of days after current date to include in active sync window. |
| `sync_interval_minutes` | Integer | No | `15` | Interval in minutes between sync cycles when running as a daemon or launchd agent. |
| `state_db_file` | String | No | `"sync_state.db"` | Relative or absolute path to SQLite mapping database. |

---

## Environment Variables

When executed via `run_sync.sh` or `launchd`:
- `LANG`: Set to `en_US.UTF-8` to ensure correct UTF-8 string encoding across all EventKit operations.
- `LC_ALL`: Set to `en_US.UTF-8`.
- `PATH`: Includes standard system paths `/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin`.
