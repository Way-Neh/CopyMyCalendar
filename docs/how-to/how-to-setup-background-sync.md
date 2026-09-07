# How-To: Set Up Background Synchronization

This guide explains how to configure automated, unattended background syncing on macOS.

---

## Method 1: Native macOS `launchd` Service (Recommended)

`launchd` is the native macOS service management daemon. It runs automatically in the background across restarts, system sleep/wake cycles, and user logins.

### 1. Install and Start the Service

From the project root directory, run:

```bash
python3 sync.py install-service
```

This creates and loads a LaunchAgent property list at:
`~/Library/LaunchAgents/com.sendtogmail.calendar-sync.plist`

### 2. Verify Service Status

Check if the service is loaded and active:

```bash
python3 sync.py status
```

### 3. Monitor Background Logs

`launchd` writes standard output and errors to the project folder:

```bash
# View standard execution logs
tail -f sync.log

# View error logs (if any)
tail -f sync.error.log
```

### 4. Adjust Sync Frequency

To change the interval (e.g., to every 30 minutes):
1. Edit `config.yaml` and update `sync_interval_minutes: 30`.
2. Re-install the service:
   ```bash
   python3 sync.py install-service
   ```

### 5. Uninstall / Stop the Service

To remove the LaunchAgent completely:

```bash
python3 sync.py uninstall-service
```

---

## Method 2: Automator Workflow & macOS Login Items

If you prefer a graphical macOS login app or want to trigger syncing from Shortcuts:

### 1. Open the Automator Workflow

Open the included [`CalendarSync.workflow`](file:///Users/ap-wayne.tan/DockerProjects/SendtoGMAIL/CalendarSync.workflow) in Automator.

### 2. Export as an Application

1. In Automator, click **File $\rightarrow$ Export...**
2. Set **File Format** to **Application**.
3. Save it as `CalendarSync.app` in `/Applications` or `~/Applications`.

### 3. Add to macOS Login Items

1. Open **System Settings $\rightarrow$ General $\rightarrow$ Login Items**.
2. Under **Open at Login**, click the **+** button.
3. Select `CalendarSync.app`.
4. Now, whenever you log in, `CalendarSync.app` starts the background daemon automatically.

---

## Method 3: Terminal Daemon Loop (`nohup`)

For quick manual background execution during an active terminal session:

```bash
# Start background daemon
nohup python3 sync.py daemon --interval 15 > daemon.log 2>&1 &

# Inspect live activity
tail -f daemon.log

# Terminate the daemon
pkill -f "sync.py daemon"
```
