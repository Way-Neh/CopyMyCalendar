# How-To: Clean and Re-sync Target Calendar

If your target calendar contains duplicates from previous manual exports or incorrect calendar selections, follow this recipe to perform a complete target wipe and fresh re-synchronization.

---

## Step 1: Wipe Target Calendar & Clear State Database

Run the `clear-target` command:

```bash
python3 sync.py clear-target -y
```

This will:
1. Delete all events in the target calendar configured in `config.yaml`.
2. Clear all mapping records from `sync_state.db`.
3. Log the cleanup action to `sync_events.log`.

> [!WARNING]
> This permanently deletes all events in the target calendar. Never set your primary personal calendar as the target.

---

## Step 2: (Optional) Re-verify Calendar Selection

If you changed calendars or need to re-verify your configuration:

```bash
python3 sync.py list-calendars
python3 sync.py setup
```

---

## Step 3: Run a Full Initial Sync

Execute a full historical and future sync pass:

```bash
python3 sync.py sync --all-time
```

This scans 10 years past and 10 years into the future, creating clean, sanitized events in your target calendar and populating a fresh SQLite state database.
