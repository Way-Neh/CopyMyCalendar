# How to Use the Native Menu Bar Application

This guide explains how to run, configure, and monitor the native macOS Menu Bar application (`gui_app.py` / `CalendarSync.app`).

---

## 1. Overview & Capabilities

The Menu Bar App is built with native macOS Cocoa (`AppKit` via PyObjC) following Apple Human Interface Guidelines (HIG):
- **Vibrant Card UI**: Visual effect materials with dark/light mode support.
- **Menu Bar Status Item**: Dynamic SF Symbols (`calendar.badge.clock` and sync animation spinner).
- **Interactive Configuration**: Source and target calendar pickers with real-time event counts.
- **Rolling Window & Frequency Steppers**: Adjust past/future sync horizons and interval minutes.
- **Live Activity Console**: High-performance SF Mono console with real-time color-coded logging and search filtering.
- **Service Control**: Toggle Start-at-Login and LaunchAgent background daemon directly from the UI.

---

## 2. Launching the App

### Option A: From Terminal
```bash
source venv/bin/activate
python3 gui_app.py
```

### Option B: macOS Application Bundle
Double-click `CalendarSync.app` in the repository root or open via Finder.

---

## 3. Configuring Sync in the GUI

1. Click the calendar icon in your macOS menu bar.
2. Select **Source Calendar** (e.g. `Work`, `Exchange`, or `Outlook`).
3. Select **Target Calendar** (e.g. `Gmail - Work`).
4. Adjust the **Rolling Window**:
   - *Days in Past*: Default `365` (1 year back).
   - *Days in Future*: Default `730` (2 years forward).
5. Set the **Sync Interval** (e.g. every `15` minutes).
6. Click **Save Settings** to persist your changes to `config.yaml`.

---

## 4. Triggering Manual Sync & Viewing Logs

- **Sync Now**: Click the **Sync Now** button at the bottom of the window to run an immediate foreground synchronization.
- **Activity Log**: Switch to the **Activity Log** tab to inspect live status outputs, event creation logs, diff statistics, and error traces.
- **Filter Logs**: Use the search box at the top of the Activity Log tab to filter lines in real time.

---

## 5. Background Daemon & Start at Login

- Toggle **Start at Login / Run as Background Service** to automatically register the LaunchAgent with macOS `launchd`.
- When enabled, syncs continue running in the background according to your configured interval even if the main UI window is closed.
