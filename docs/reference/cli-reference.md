# Reference: CLI Reference

The CLI entrypoint is [`sync.py`](file:///Users/ap-wayne.tan/DockerProjects/SendtoGMAIL/sync.py). Commands can be executed using positional subcommands or legacy direct flags.

---

## Synopsis

```bash
python3 sync.py <subcommand> [options...]
```

---

## Subcommands

### `list-calendars`
Scans all macOS calendars, displays account affiliations, unique `calendarIdentifier` keys, and event counts for the past/future 1 year.
```bash
python3 sync.py list-calendars
```

### `setup`
Launches the interactive configuration wizard to select source and target calendars, configure time windows, and save `config.yaml`.
```bash
python3 sync.py setup
```

### `sync`
Executes a single synchronization pass between source and target calendars.
```bash
python3 sync.py sync [flags]
```

**Options:**
- `--source-id <ID>`: Override the configured source calendar identifier.
- `--target-id <ID>`: Override the configured target calendar identifier.
- `--days-past <INT>`: Override the number of past rolling days (e.g. `30`).
- `--days-future <INT>`: Override the number of future rolling days (e.g. `180`).
- `--all-time`: Expands the sync window to ±10 years (3650 days).
- `--dry-run`: Calculates the diff and prints planned changes without writing to the target calendar.

### `daemon`
Runs a continuous foreground or background polling loop.
```bash
python3 sync.py daemon [--interval <MINUTES>] [--all-time]
```

**Options:**
- `--interval <INT>`: Time in minutes to sleep between sync cycles (default: `15`, minimum: `1`).
- `--all-time`: Use a 10-year rolling window for each cycle.

### `clear-target`
Deletes all events within the target calendar and resets mapping entries in `sync_state.db`.
```bash
python3 sync.py clear-target [-y | --yes]
```

**Options:**
- `-y`, `--yes`: Bypass confirmation prompt and delete immediately.

### `find`
Performs a global case-insensitive search across all macOS calendars within ±10 years.
```bash
python3 sync.py find "<KEYWORD>"
```

### `dump-events`
Exports all events from the source calendar to `events_dump.txt` formatted in local machine time.
```bash
python3 sync.py dump-events [--all-time]
```

### `log`
Displays the latest lines from `sync_events.log`.
```bash
python3 sync.py log [-n <LINES>]
```

**Options:**
- `-n`, `--lines <INT>`: Number of trailing log lines to output (default: `100`).

### `reset-state`
Deletes the local `sync_state.db` file.
```bash
python3 sync.py reset-state
```

### `install-service`
Generates and registers the macOS `launchd` LaunchAgent (`com.sendtogmail.calendar-sync.plist`).
```bash
python3 sync.py install-service
```

### `uninstall-service`
Unloads and deletes the macOS `launchd` LaunchAgent.
```bash
python3 sync.py uninstall-service
```

### `status`
Displays current calendar configuration, state database timestamps, and `launchd` agent status.
```bash
python3 sync.py status
```

---

## Exit Codes

- `0`: Operation completed successfully.
- `1`: Operation failed due to configuration, permission, or runtime error.
