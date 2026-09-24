# SendtoGMAIL (CalendarSync) Domain Context

The macOS Calendar to Gmail synchronization system mirrors work calendar events into a sanitized target calendar within the macOS ecosystem without leaking private metadata.

## Language

### Core Entities

**Source Calendar**:
The primary calendar containing original work meetings, appointments, and schedules (e.g. Exchange, Outlook, iCloud).
_Avoid_: Upstream calendar, master calendar, parent calendar

**Target Calendar**:
The dedicated destination calendar (typically a Google/Gmail calendar configured in macOS Calendar) where sanitized event instances are published.
_Avoid_: Downstream calendar, slave calendar, mirror calendar

**Sanitized Event**:
A calendar event stripped of all sensitive metadata, preserving only start time, end time, title, and all-day status.
_Avoid_: Masked event, filtered event, redacted event

**Event Mapping**:
A persisted correlation entry in the state database binding a source event instance to its corresponding target event instance.
_Avoid_: Link record, sync pair, association

### Synchronization & Diffing

**Rolling Window**:
The dynamic time boundary (e.g. 365 days past to 730 days future) within which events are queried, compared, and reconciled.
_Avoid_: Date range filter, sync bracket

**Instance Expansion**:
The process of expanding a recurring event rule (RRULE) into discrete, individual occurrences with timestamped identifiers.
_Avoid_: Recurrence unfolding, event unrolling

**Content Hash**:
A canonical SHA-256 digest computed from an event's title, start timestamp, end timestamp, and all-day flag to detect modifications.
_Avoid_: Checksum, fingerprint, revision token

**Dry Run**:
A simulation mode that computes and reports diff operations (creates, updates, deletes) without writing any mutations to disk or calendars.
_Avoid_: Test run, preview mode

### Interfaces & Infrastructure

**Menu Bar App**:
The native macOS Cocoa status bar application providing visual status indicators, interactive configuration, live logs, and manual sync triggers.
_Avoid_: Tray app, system tray widget, desktop client

**LaunchAgent Service**:
The background daemon managed by macOS `launchd` running periodic unattended synchronizations.
_Avoid_: Cron job, system daemon, background worker
