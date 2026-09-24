# 2. SQLite State Store and SHA-256 Fingerprinting for Idempotent Diffing

## Context
EventKit and Outlook calendar event identifiers can shift across synchronization cycles, and full-calendar scans across years of events create severe I/O bottlenecks and potential rate-limiting when communicating with upstream calendar providers.

## Decision
We use a lightweight local SQLite database (`sync_state.db`) maintaining an `event_mappings` table. For each source event instance, we generate a canonical SHA-256 content hash of `{title, start_iso, end_iso, is_all_day}` and store it alongside the mapped target event identifier.

## Consequences
- **Idempotency**: Repeated sync passes compare local hashes without making redundant write operations to target calendars.
- **Orphan Cleanup**: Deletions in source calendars are detected when mapped source IDs vanish from the rolling window.
- **State Recovery**: If the database is lost or corrupted, clearing the target calendar and re-syncing cleanly rebuilds the state table.
