# Getting Started with Calendar Sync

This tutorial takes you through setting up and running your first calendar synchronization from scratch. By the end of this tutorial, you will have connected your source calendar (e.g., Work / Exchange) to your target Gmail calendar inside the macOS Calendar app and completed a verified test sync.

---

## Prerequisites

Before starting, ensure you have:
1. **macOS 12.0 (Monterey)** or newer.
2. **Python 3.9+** installed (`python3 --version`).
3. Both calendars added to your macOS **Calendar app** (**Calendar $\rightarrow$ Settings $\rightarrow$ Accounts**):
   - **Source Calendar**: Your corporate, Exchange, iCloud, or work calendar.
   - **Target Calendar**: A secondary Google / Gmail calendar (e.g., named "Gmail - Work" or "Synced Work").

> [!TIP]
> We recommend creating a dedicated secondary calendar in Google Calendar (e.g. named "Work Mirror") rather than syncing directly into your primary personal calendar. This allows you to easily toggle visibility or delete synced events without affecting personal appointments.

---

## Step 1: Clone and Set Up the Python Environment

Open your terminal and navigate to the project repository:

```bash
cd /Users/ap-wayne.tan/DockerProjects/SendtoGMAIL
```

Create an isolated virtual environment and activate it:

```bash
python3 -m venv venv
source venv/bin/activate
```

Install the required dependencies:

```bash
pip install -r requirements.txt
```

---

## Step 2: Grant macOS Calendar Permissions

macOS protects calendar access via Transparency, Consent, and Control (TCC).

1. Run the calendar list command to trigger the permission prompt:
   ```bash
   python3 sync.py list-calendars
   ```
2. A system prompt will appear: **"Terminal would like to access your Calendar"**. Click **OK** / **Allow Full Access**.
3. If no prompt appears, manually enable it in **System Settings $\rightarrow$ Privacy & Security $\rightarrow$ Calendars** and toggle your terminal app on.

Once permission is granted, you will see a table listing all calendars detected on your Mac along with their account names and event counts.

---

## Step 3: Run the Interactive Setup Wizard

Run the configuration wizard:

```bash
python3 sync.py setup
```

The wizard will guide you through 4 simple steps:

1. **Select Source Calendar**: Enter the number corresponding to your source calendar (e.g. `Work`).
2. **Select Target Calendar**: Enter the number corresponding to your target Gmail calendar (e.g. `Gmail - Work`).
3. **Select Rolling Time Window**:
   - Days in past to sync (Default: `365` days).
   - Days into future to sync (Default: `730` days).
4. **Select Sync Interval**: Background interval in minutes (Default: `15`).

The wizard will generate and save `config.yaml` using the exact unique system identifiers (`calendarIdentifier`) for 100% collision-free matching.

---

## Step 4: Perform a Dry-Run Sync

Before writing any events, perform a dry run to preview what changes would be made:

```bash
python3 sync.py sync --dry-run
```

You will see a summary table showing:
- Source events detected within the window.
- Number of events to create, update, delete, or leave unchanged.

---

## Step 5: Execute Your First Real Sync

Now run a live synchronization pass:

```bash
python3 sync.py sync
```

You should see output similar to:

```text
Sync Results (2026-09-03 01:30:00 +08)
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┓
┃ Metric                              ┃ Count ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━┩
│ Total Source Events in Window       │ 142   │
│ New Events Created in Target        │ 142   │
│ Modified Events Updated in Target   │ 0     │
│ Deleted Events Removed from Target  │ 0     │
│ Unchanged Events                    │ 0     │
└─────────────────────────────────────┴───────┘
Detailed audit log written to: sync_events.log
Sync completed successfully!
```

---

## Step 6: Verify in macOS Calendar & Google Calendar

1. Open the **macOS Calendar app**.
2. Enable both your source and target calendars in the sidebar.
3. Verify that your target calendar contains all corresponding events with identical start and end times.
4. Click on any synced event in the target calendar to confirm that meeting notes, video URLs, and attendee lists were safely stripped.
5. Open [Google Calendar on the web](https://calendar.google.com) to verify that macOS synced the new entries upstream to Google servers.

---

## Next Steps

Congratulations! You have completed your first calendar sync.

- **Automate background synchronization**: See [How-To: Set Up Background Sync](file:///Users/ap-wayne.tan/DockerProjects/SendtoGMAIL/docs/how-to/how-to-setup-background-sync.md).
- **Inspect execution logs and debug**: See [How-To: Troubleshoot and Audit](file:///Users/ap-wayne.tan/DockerProjects/SendtoGMAIL/docs/how-to/how-to-troubleshoot-and-audit.md).
- **Explore all subcommands**: See [Reference: CLI Reference](file:///Users/ap-wayne.tan/DockerProjects/SendtoGMAIL/docs/reference/cli-reference.md).
