# How-To: Troubleshoot and Audit Calendar Synchronization

This guide covers recipes for debugging synchronization discrepancies, locating specific events across all macOS calendars, inspecting audit trails, and resolving common errors.

---

## 1. Search for an Event Across All Mac Calendars

When you suspect an event is missing or not syncing, search all calendars on your Mac (including iCloud, Exchange, Google, Local):

```bash
python3 sync.py find "Keyword or Meeting Title"
```

**Example Output:**
```text
Search Results for 'Architecture Review' (2 found)
┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┓
┃ Account / Source ┃ Calendar Name ┃ Unique ID        ┃ Local Time       ┃ Event Title         ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━┩
│ Exchange         │ Work          │ D16938BC-9D12... │ 2026-09-04 10:00 │ Architecture Review │
│ Google           │ Gmail - Work  │ 8E04C741-94E5... │ 2026-09-04 10:00 │ Architecture Review │
└──────────────────┴────────━━━━━━━┴━━━━━━━━━━━━━━━━━━┴━━━━━━━━━━━━━━━━━━┴━━━━━━━━━━━━━━━━━━━━━┘
```

---

## 2. Dump All Events in Source Calendar to a Text File

To audit every event detected within your source calendar over an extended date range:

```bash
# Dump past 10 years and future 10 years
python3 sync.py dump-events --all-time
```

This writes a clean, chronologically sorted list to `events_dump.txt` formatted in machine local time.

---

## 3. Inspect the Event-by-Event Audit Log

The tool maintains a continuous audit log in `sync_events.log`. To view the most recent 100 entries:

```bash
python3 sync.py log -n 100
```

Or watch it in real time:

```bash
tail -f sync_events.log
```

Log entry tags:
- `[CREATED]` : A new event was added to the target calendar.
- `[UPDATED]` : An event whose title or time changed was modified in the target calendar.
- `[DELETED]` : An event removed from the source calendar was deleted from the target calendar.
- `[UNCHANGED]`: An event whose content hash matches the state database was untouched.
- `[ERR CREATE]` / `[ERR UPDATE]` / `[ERR DELETE]`: An error occurred during EventKit modification.

---

## 4. Resolving Common Issues

### Issue: `PermissionError: Calendar access was denied by macOS`
**Cause**: The terminal application or `zsh` subshell lacks macOS TCC calendar permissions.
**Solution**:
1. Open **System Settings $\rightarrow$ Privacy & Security $\rightarrow$ Calendars**.
2. Toggle permissions ON for your terminal app (Terminal, iTerm, VS Code, etc.).
3. If permissions are in a broken state, reset them:
   ```bash
   tccutil reset Calendar
   ```

### Issue: Events Not Appearing in Google Calendar Web UI
**Cause**: The events are written to the macOS Calendar app local store, but macOS has not yet synced upstream to Google servers.
**Solution**:
1. Open the **macOS Calendar app**.
2. Press `Cmd + R` to force an immediate server refresh.
3. Check **Calendar $\rightarrow$ Settings $\rightarrow$ Accounts** to ensure your Google account is connected and not requesting re-authentication.

### Issue: Events Shifted by One Hour (Timezone Mismatch)
**Cause**: System timezone or daylight saving offset discrepancy.
**Solution**:
- The sync engine normalizes all events using `datetime.astimezone()`. Ensure that **System Settings $\rightarrow$ General $\rightarrow$ Date & Time** has "Set time zone automatically using your current location" enabled.
