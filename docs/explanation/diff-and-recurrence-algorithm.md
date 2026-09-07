# Explanation: Diff Engine & Recurrence Handling

This document explains the mathematical and algorithmic foundations of change detection and recurring event expansion used in `sync_engine.py`.

---

## 1. The Challenge of Recurring Events in EventKit

In macOS EventKit (and the iCalendar RFC 5545 specification):
- A recurring series is defined by a single parent event entity (`EKEvent`) with one or more `EKRecurrenceRule` records.
- Individual instances in the series do **not** have unique database rows until an exception occurs (e.g. one specific meeting is rescheduled).
- When syncing directly to a secondary target calendar, creating a duplicate recurrence rule often causes desynchronization when single occurrences are modified or deleted in the source calendar.

---

## 2. Solution: Compound Instance IDs & Concrete Expansion

To solve this, the sync engine expands all recurring series into concrete instances across the active rolling window:

```
Source Recurring Series (Base ID: "ABC-123")
  ├── Occurrence 1 (2026-09-01 10:00) -> ID: "ABC-123_1788220800"
  ├── Occurrence 2 (2026-09-08 10:00) -> ID: "ABC-123_1788825600"
  └── Occurrence 3 (2026-09-15 10:00) -> ID: "ABC-123_1789430400"
```

Each instance is identified by:
$$\text{Instance ID} = \text{base\_id} + \text{"\_"} + \text{raw\_start\_timestamp}$$

Each expanded instance is synced to the target calendar as an independent, discrete single event. This guarantees that:
1. Moving or deleting a single occurrence only affects that specific instance in the target calendar.
2. No complex recurrence rule synchronization bugs occur between different calendar backends (e.g. Exchange $\leftrightarrow$ Google).

---

## 3. SHA-256 Content Hashing

To avoid unnecessary writes and maintain lightning-fast sync cycles, each event generates a canonical JSON representation:

```json
{
  "end": "2026-09-04T11:00:00+08:00",
  "is_all_day": false,
  "start": "2026-09-04T10:00:00+08:00",
  "title": "Architecture Review"
}
```

$$\text{content\_hash} = \text{SHA-256}(\text{canonical\_json})$$

The engine compares this hash with the stored hash in SQLite:
- If hashes match and the target event exists $\rightarrow$ **Unchanged** (0 I/O writes).
- If hashes differ $\rightarrow$ **Update** target event with new title/time.
- If source event is absent from source calendar but present in mappings within the window $\rightarrow$ **Delete** target event.
