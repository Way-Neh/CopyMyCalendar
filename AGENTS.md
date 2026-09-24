# AGENTS.md

Instructions and operational reference for AI coding agents working in this repository.

## Context Pointers

- [**Domain Vocabulary (`CONTEXT.md`)**](file:///Users/ap-wayne.tan/DockerProjects/SendtoGMAIL/CONTEXT.md): Canonical domain terms (`Source Calendar`, `Target Calendar`, `Sanitized Event`, `Instance Expansion`).
- [**Architecture & Data Flow (`ARCHITECTURE.md`)**](file:///Users/ap-wayne.tan/DockerProjects/SendtoGMAIL/ARCHITECTURE.md): System diagrams, module responsibilities, and recurrence handling.
- [**Architecture Decisions (`docs/adr/`)**](file:///Users/ap-wayne.tan/DockerProjects/SendtoGMAIL/docs/adr/): Rationale for EventKit/AppleScript over OAuth APIs and PyObjC GUI.
- [**Diátaxis Documentation (`docs/`)**](file:///Users/ap-wayne.tan/DockerProjects/SendtoGMAIL/docs/): Complete tutorials, how-to guides, and reference specs.

---

## Operating Environment

- **OS**: macOS (Darwin 12.0+)
- **Python**: 3.9+ with virtual environment at `venv/`
- **Native Bindings**: PyObjC (`pyobjc-framework-EventKit`, `pyobjc-framework-Cocoa`)
- **State Store**: SQLite (`sync_state.db`)
- **Configuration**: `config.yaml` (copy from `config.yaml.example` if missing)

---

## Agent Workflows & Commands

### 1. Running Tests
Run unit and integration tests using Python directly from the activated virtual environment:

```bash
# Core sync engine tests
python3 test_sync_engine.py

# Outlook AppleScript client tests
python3 test_outlook_calendar.py

# GUI App logic tests
python3 test_gui_app.py
```
*Completion Criterion*: All test suites pass with returncode `0` and no unhandled exceptions.

### 2. Testing CLI Sync (Dry Run)
Before modifying calendar stores or database state, verify diff logic in dry-run mode:

```bash
python3 sync.py sync --dry-run
```
*Completion Criterion*: Diff summary outputs `to_create`, `to_update`, `to_delete`, and `unchanged` counts without altering target calendar.

### 3. Launching GUI App
Launch the native menu bar interface:

```bash
python3 gui_app.py
```
*Completion Criterion*: Menu bar status item appears with `calendar.badge.clock` or loading spinner icon.

### 4. Inspecting SQLite State Store
Query the local SQLite database for mapping integrity:

```bash
sqlite3 sync_state.db "SELECT count(*) FROM event_mappings;"
sqlite3 sync_state.db "SELECT * FROM sync_meta;"
```

---

## Code Modification Rules

1. **Privacy Invariant**: When creating target calendar events in `mac_calendar.py` or `google_cal.py`, retain strictly sanitized fields: `title`, `start`, `end`, and `is_all_day`. Exclude `notes`, `description`, `location`, `url`, `attendees`, and `alarms`.
2. **Local Time Reference**: Preserve machine local time (`datetime.datetime`) across all timezone and epoch conversions to prevent 1-hour daylight saving or timezone shifts.
3. **Idempotent Hashes**: Compute `content_hash` using `hashlib.sha256` on formatted ISO strings `{title, start_iso, end_iso, is_all_day}`.
4. **Graceful Permission Failures**: Catch macOS TCC `-1743` automation and Calendar access denials gracefully with human-readable troubleshooting guidance.
