#!/usr/bin/env python3
"""
gui_app.py - Native macOS CalendarSync Menu Bar Application.
Features:
- Apple HIG System Settings card-style interface with NSVisualEffectView vibrancy
- Menu bar status item with dynamic SF Symbols (calendar.badge.clock <-> arrow.triangle.2.circlepath)
- Segmented control switching between Configuration and Activity Logs
- Source and Target calendar popups with live account info and event counts
- Rolling window and sync interval stepper controls
- Live SF Mono activity log console with real-time filtering, syntax coloring, and auto-scroll
- Non-blocking background scheduler running at configured interval with mutex locking
- Native macOS notifications and LaunchAgent Start-at-Login management
"""

import os
import sys
import glob
import time
import yaml
import plistlib
import threading
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

# Auto-inject project virtual environment site-packages if present
_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
_site_packages = glob.glob(os.path.join(_PROJECT_DIR, "venv", "lib", "python*", "site-packages"))
for _sp in _site_packages:
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

import objc
from Foundation import (
    NSObject,
    NSMakeRect,
    NSMakeSize,
    NSPoint,
    NSMakeRange,
    NSURL,
    NSAttributedString,
    NSMutableAttributedString,
    NSDictionary,
    NSRunLoop,
    NSDate,
    NSTimer,
)
import AppKit
from AppKit import (
    NSApplication,
    NSApp,
    NSWindow,
    NSView,
    NSBox,
    NSBoxCustom,
    NSTextField,
    NSButton,
    NSPopUpButton,
    NSStepper,
    NSSegmentedControl,
    NSSearchField,
    NSScrollView,
    NSTextView,
    NSFont,
    NSFontWeightBold,
    NSFontWeightSemibold,
    NSFontWeightMedium,
    NSFontWeightRegular,
    NSColor,
    NSImage,
    NSImageView,
    NSMenu,
    NSMenuItem,
    NSStatusBar,
    NSVariableStatusItemLength,
    NSSquareStatusItemLength,
    NSVisualEffectView,
    NSVisualEffectBlendingModeBehindWindow,
    NSVisualEffectMaterialSidebar,
    NSVisualEffectMaterialUnderWindowBackground,
    NSVisualEffectStateActive,
    NSAlert,
    NSAlertStyleInformational,
    NSAlertStyleWarning,
    NSAlertStyleCritical,
    NSAlertFirstButtonReturn,
    NSAlertSecondButtonReturn,
    NSWorkspace,
    NSPasteboard,
    NSPasteboardTypeString,
    NSBezelStyleRounded,
    NSBezelStyleRegularSquare,
    NSControlStateValueOn,
    NSControlStateValueOff,
    NSSegmentStyleRounded,
    NSSegmentSwitchTrackingSelectOne,
    NSWindowStyleMaskTitled,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskFullSizeContentView,
    NSBackingStoreBuffered,
    NSEventModifierFlagCommand,
    NSFontAttributeName,
    NSForegroundColorAttributeName,
)

from mac_calendar import MacCalendarClient, EVENTKIT_AVAILABLE
from sync_engine import SyncStateStore, SyncEngine, SYNC_LOG_FILE

def get_app_data_dir() -> str:
    """Return user Application Support directory when running standalone, or project dir in dev mode."""
    if getattr(sys, "frozen", False):
        app_support = os.path.expanduser("~/Library/Application Support/CalendarSync")
        os.makedirs(app_support, exist_ok=True)
        return app_support
    return _PROJECT_DIR


def get_app_data_path(filename: str) -> str:
    """Resolve file path relative to app data directory or project directory."""
    if os.path.isabs(filename):
        return filename
    return os.path.join(get_app_data_dir(), filename)


CONFIG_FILE = get_app_data_path("config.yaml")
LAUNCH_AGENT_LABEL = "com.sendtogmail.calendarsync"
LAUNCH_AGENT_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"


# ==============================================================================
# Helper: Thread-safe dispatch to Cocoa Main Run Loop
# ==============================================================================
class MainThreadDispatcher(NSObject):
    """Dispatches Python callables safely onto the main Cocoa UI thread."""
    _instance = None
    _callbacks = {}
    _counter = 0
    _lock = threading.Lock()

    @classmethod
    def shared(cls):
        if cls._instance is None:
            cls._instance = cls.alloc().init()
        return cls._instance

    @classmethod
    def run_on_main(cls, func, *args, **kwargs):
        if threading.current_thread() is threading.main_thread():
            try:
                func(*args, **kwargs)
            except Exception as e:
                print(f"[MainThreadDispatcher] Direct execution error: {e}", file=sys.stderr)
            return

        with cls._lock:
            cls._counter += 1
            cid = cls._counter
            cls._callbacks[cid] = lambda: func(*args, **kwargs)
        cls.shared().performSelectorOnMainThread_withObject_waitUntilDone_(
            "executeCallback:", cid, False
        )

    def executeCallback_(self, cid):
        with MainThreadDispatcher._lock:
            cb = MainThreadDispatcher._callbacks.pop(int(cid), None)
        if cb:
            try:
                cb()
            except Exception as e:
                print(f"[MainThreadDispatcher] Callback error: {e}", file=sys.stderr)


# ==============================================================================
# Notifications & LaunchAgent Helpers
# ==============================================================================
def send_mac_notification(title: str, subtitle: str, message: str):
    """Send a native macOS user notification with osascript fallback."""
    try:
        from Foundation import NSUserNotification, NSUserNotificationCenter
        notification = NSUserNotification.alloc().init()
        notification.setTitle_(title)
        if subtitle:
            notification.setSubtitle_(subtitle)
        notification.setInformativeText_(message)
        center = NSUserNotificationCenter.defaultUserNotificationCenter()
        center.deliverNotification_(notification)
        return
    except Exception:
        pass

    try:
        sub_clause = f' subtitle "{subtitle}"' if subtitle else ""
        escaped_msg = message.replace('"', '\\"')
        escaped_title = title.replace('"', '\\"')
        script = f'display notification "{escaped_msg}" with title "{escaped_title}"{sub_clause}'
        subprocess.run(["osascript", "-e", script], check=False, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def is_start_at_login_enabled() -> bool:
    """Check if the LaunchAgent plist is installed in ~/Library/LaunchAgents."""
    return LAUNCH_AGENT_PATH.exists()


def set_start_at_login(enabled: bool) -> bool:
    """Install or uninstall the LaunchAgent for CalendarSync."""
    uid = os.getuid()
    if not enabled:
        if LAUNCH_AGENT_PATH.exists():
            try:
                subprocess.run(
                    ["launchctl", "bootout", f"gui/{uid}", str(LAUNCH_AGENT_PATH)],
                    stderr=subprocess.DEVNULL,
                    check=False
                )
            except Exception:
                pass
            LAUNCH_AGENT_PATH.unlink(missing_ok=True)
        return False
    else:
        LAUNCH_AGENT_PATH.parent.mkdir(parents=True, exist_ok=True)
        if getattr(sys, "frozen", False):
            launcher = sys.executable
        else:
            launcher = os.path.join(_PROJECT_DIR, "CalendarSync.app", "Contents", "MacOS", "CalendarSync")
            if not os.path.exists(launcher):
                launcher = os.path.join(_PROJECT_DIR, "run_sync.sh")

        plist_data = {
            "Label": LAUNCH_AGENT_LABEL,
            "ProgramArguments": [launcher, "--minimized"],
            "RunAtLoad": True,
            "ProcessType": "Interactive",
            "EnvironmentVariables": {
                "LANG": "en_US.UTF-8",
                "LC_ALL": "en_US.UTF-8"
            }
        }
        with open(LAUNCH_AGENT_PATH, "wb") as f:
            plistlib.dump(plist_data, f)

        try:
            subprocess.run(
                ["launchctl", "bootstrap", f"gui/{uid}", str(LAUNCH_AGENT_PATH)],
                check=True,
                stderr=subprocess.DEVNULL
            )
        except Exception:
            try:
                subprocess.run(["launchctl", "load", "-w", str(LAUNCH_AGENT_PATH)], check=False, stderr=subprocess.DEVNULL)
            except Exception:
                pass
        return True


# ==============================================================================
# Configuration Persistence
# ==============================================================================
def load_app_config() -> dict:
    """Load configuration from config.yaml."""
    default_cfg = {
        "source_calendar_name": "",
        "source_calendar_id": "",
        "target_calendar_name": "",
        "target_calendar_id": "",
        "rolling_days_past": 7,
        "rolling_days_future": 30,
        "sync_interval_minutes": 15,
        "state_db_file": "sync_state.db",
        "run_in_menu_bar_only": True,
    }
    if not os.path.exists(CONFIG_FILE):
        # Look for dev config file in repo dir if different
        dev_config = os.path.join(_PROJECT_DIR, "config.yaml")
        if os.path.exists(dev_config) and dev_config != CONFIG_FILE:
            try:
                with open(dev_config, "r") as f:
                    loaded = yaml.safe_load(f) or {}
                    default_cfg.update(loaded)
                    return default_cfg
            except Exception:
                pass

        bundle_dir = getattr(sys, "_MEIPASS", _PROJECT_DIR)
        example_file = os.path.join(bundle_dir, "config.yaml.example")
        if not os.path.exists(example_file):
            example_file = os.path.join(_PROJECT_DIR, "config.yaml.example")
        if os.path.exists(example_file):
            try:
                with open(example_file, "r") as f:
                    loaded = yaml.safe_load(f) or {}
                    default_cfg.update(loaded)
                    return default_cfg
            except Exception:
                pass
        return default_cfg
    try:
        with open(CONFIG_FILE, "r") as f:
            loaded = yaml.safe_load(f) or {}
            merged = dict(default_cfg)
            merged.update(loaded)
            return merged
    except Exception:
        return default_cfg


def save_app_config(config: dict):
    """Save configuration to config.yaml."""
    with open(CONFIG_FILE, "w") as f:
        yaml.dump(config, f, default_flow_style=False)


# ==============================================================================
# Background Scheduler & Sync Worker
# ==============================================================================
class SyncScheduler:
    """Thread-safe background scheduler and sync worker."""

    def __init__(self, on_state_change=None, on_log_update=None):
        self.on_state_change = on_state_change
        self.on_log_update = on_log_update
        self._lock = threading.Lock()
        self.is_syncing = False
        self.last_sync_time: Optional[float] = None
        self.last_sync_stats: Optional[dict] = None
        self.last_error: Optional[str] = None
        self.interval_seconds = 15 * 60
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._reload_interval_from_config()

    def _reload_interval_from_config(self):
        cfg = load_app_config()
        mins = cfg.get("sync_interval_minutes", 15)
        try:
            mins = int(mins)
        except (ValueError, TypeError):
            mins = 15
        self.interval_seconds = max(60, mins * 60)

    def start(self):
        """Start the background scheduler thread."""
        if self._thread is None or not self._thread.is_alive():
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._scheduler_loop, daemon=True, name="SyncScheduler")
            self._thread.start()

    def stop(self):
        """Signal background scheduler to stop."""
        self._stop_event.set()

    def update_interval_minutes(self, minutes: int):
        """Update scheduler interval dynamically."""
        self.interval_seconds = max(60, int(minutes) * 60)

    def _scheduler_loop(self):
        # Background check loop
        while not self._stop_event.is_set():
            if self._stop_event.wait(timeout=5):
                break

            now = time.time()
            # If never synced, check DB for previous sync timestamp
            if self.last_sync_time is None:
                cfg = load_app_config()
                db_path = get_app_data_path(cfg.get("state_db_file", "sync_state.db"))
                if os.path.exists(db_path):
                    store = SyncStateStore(db_path)
                    last_str = store.get_meta("last_sync_time")
                    if last_str:
                        try:
                            last_dt = datetime.fromisoformat(last_str)
                            self.last_sync_time = last_dt.timestamp()
                        except Exception:
                            self.last_sync_time = now
                    else:
                        self.last_sync_time = now
                else:
                    self.last_sync_time = now

            if not self.is_syncing and (now - self.last_sync_time >= self.interval_seconds):
                cfg = load_app_config()
                # Only trigger automatic background sync if both calendars are configured
                if cfg.get("source_calendar_id") and cfg.get("target_calendar_id"):
                    self.trigger_sync(dry_run=False, is_manual=False)

    def trigger_sync(self, dry_run: bool = False, is_manual: bool = True) -> bool:
        """Initiate sync in a dedicated background worker thread."""
        with self._lock:
            if self.is_syncing:
                return False
            self.is_syncing = True

        worker = threading.Thread(
            target=self._sync_worker,
            args=(dry_run, is_manual),
            daemon=True,
            name="SyncWorker"
        )
        worker.start()
        return True

    def _sync_worker(self, dry_run: bool, is_manual: bool):
        try:
            MainThreadDispatcher.run_on_main(self._notify_started, dry_run)

            cfg = load_app_config()
            src_id = cfg.get("source_calendar_id")
            tgt_id = cfg.get("target_calendar_id")
            src_name = cfg.get("source_calendar_name", "Source")
            tgt_name = cfg.get("target_calendar_name", "Target")
            days_past = int(cfg.get("rolling_days_past", 7))
            days_future = int(cfg.get("rolling_days_future", 30))
            db_file = get_app_data_path(cfg.get("state_db_file", "sync_state.db"))
            log_file = get_app_data_path(SYNC_LOG_FILE)

            if not src_id or not tgt_id:
                raise ValueError("Source or Target calendar is not configured. Please open Configuration.")

            if src_id == tgt_id:
                raise ValueError("Source and Target calendars cannot be the same.")

            client = MacCalendarClient()
            store = SyncStateStore(db_file)
            engine = SyncEngine(
                mac_client=client,
                state_store=store,
                source_calendar_id=src_id,
                target_calendar_id=tgt_id,
                source_calendar_name=src_name,
                target_calendar_name=tgt_name,
                days_past=days_past,
                days_future=days_future
            )

            stats = engine.sync(dry_run=dry_run, log_file=log_file)
            self.last_sync_stats = stats
            self.last_error = None
            if not dry_run:
                self.last_sync_time = time.time()

            MainThreadDispatcher.run_on_main(self._notify_finished, stats, None, dry_run, is_manual)

        except Exception as e:
            self.last_error = str(e)
            MainThreadDispatcher.run_on_main(self._notify_finished, None, str(e), dry_run, is_manual)

        finally:
            with self._lock:
                self.is_syncing = False

    def _notify_started(self, dry_run: bool):
        if self.on_state_change:
            self.on_state_change(is_syncing=True, stats=None, error=None, dry_run=dry_run)

    def _notify_finished(self, stats: Optional[dict], error: Optional[str], dry_run: bool, is_manual: bool):
        if self.on_state_change:
            self.on_state_change(is_syncing=False, stats=stats, error=error, dry_run=dry_run)
        if self.on_log_update:
            self.on_log_update()

        # macOS Notification for events synced or failures
        if error:
            send_mac_notification("CalendarSync Alert", "Sync Failed", error)
        elif stats:
            created = stats.get("created", 0)
            updated = stats.get("updated", 0)
            deleted = stats.get("deleted", 0)
            prefix = "[Dry Run] " if dry_run else ""
            if created > 0 or updated > 0 or deleted > 0:
                summary = f"{prefix}Updated: +{created} created, ~{updated} updated, -{deleted} deleted"
                send_mac_notification("CalendarSync", "Sync Complete", summary)
            elif is_manual:
                send_mac_notification("CalendarSync", "Sync Complete", f"{prefix}All calendars are up to date.")


# ==============================================================================
# UI Syntax Colorizer for Activity Logs
# ==============================================================================
def colorize_log_text(raw_text: str, filter_query: str = "") -> NSMutableAttributedString:
    """Format raw log text into an attributed string with SF Mono and Apple HIG coloring."""
    mas = NSMutableAttributedString.alloc().init()
    lines = raw_text.splitlines()

    font_mono = NSFont.monospacedSystemFontOfSize_weight_(11.5, NSFontWeightRegular)
    font_mono_bold = NSFont.monospacedSystemFontOfSize_weight_(11.5, NSFontWeightBold)

    col_text = NSColor.labelColor()
    col_dim = NSColor.secondaryLabelColor()
    col_green = NSColor.systemGreenColor()
    col_blue = NSColor.systemBlueColor()
    col_orange = NSColor.systemOrangeColor()
    col_red = NSColor.systemRedColor()
    col_purple = NSColor.systemPurpleColor()
    col_teal = NSColor.systemTealColor()

    query_lower = filter_query.strip().lower()

    for line in lines:
        if query_lower and query_lower not in line.lower():
            continue

        color = col_text
        font = font_mono

        if "[CREATED]" in line:
            color = col_green
            font = font_mono_bold
        elif "[UPDATED]" in line:
            color = col_blue
            font = font_mono_bold
        elif "[DELETED]" in line or "[ERR" in line:
            color = col_red
            font = font_mono_bold
        elif any(tag in line for tag in ("[TO CREATE]", "[TO UPDATE]", "[TO DELETE]")):
            color = col_orange
        elif "[UNCHANGED]" in line:
            color = col_dim
        elif line.startswith("===") or line.startswith("---"):
            color = col_dim
        elif "SYNC RUN" in line or "CLEAR TARGET" in line:
            color = col_purple
            font = font_mono_bold
        elif any(k in line for k in ("SOURCE CALENDAR", "TARGET CALENDAR", "WINDOW", "TOTAL DETECTED", "PLAN", "MODE")):
            color = col_teal

        attrs = {
            NSFontAttributeName: font,
            NSForegroundColorAttributeName: color
        }
        attr_dict = NSDictionary.dictionaryWithDictionary_(attrs)
        line_str = NSAttributedString.alloc().initWithString_attributes_(line + "\n", attr_dict)
        mas.appendAttributedString_(line_str)

    return mas


# ==============================================================================
# Window Delegate
# ==============================================================================
class WindowDelegate(NSObject):
    """Handles window close events to hide instead of destroy the window."""
    def windowShouldClose_(self, window):
        window.orderOut_(None)
        return False


# ==============================================================================
# Main Settings & Activity Window Controller
# ==============================================================================
class MainWindowController(NSObject):
    """Manages the modern macOS System Settings card-style window."""

    def init(self):
        self = objc.super(MainWindowController, self).init()
        if self is None:
            return None

        self.scheduler: Optional[SyncScheduler] = None
        self.cached_calendars: List[Dict[str, Any]] = []
        self._window_delegate = WindowDelegate.alloc().init()

        self._build_window()
        return self

    def _build_window(self):
        # 720 x 680 window with modern titlebar-less style
        rect = NSMakeRect(200, 200, 720, 680)
        style = (
            NSWindowStyleMaskTitled |
            NSWindowStyleMaskClosable |
            NSWindowStyleMaskMiniaturizable |
            NSWindowStyleMaskResizable |
            NSWindowStyleMaskFullSizeContentView
        )
        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect, style, NSBackingStoreBuffered, False
        )
        self.window.setReleasedWhenClosed_(False)
        self.window.setTitle_("CalendarSync")
        self.window.setTitlebarAppearsTransparent_(True)
        self.window.setTitleVisibility_(AppKit.NSWindowTitleHidden)
        self.window.setMovableByWindowBackground_(True)
        self.window.setMinSize_(NSMakeSize(680, 600))
        self.window.setDelegate_(self._window_delegate)

        # Frosted vibrancy backdrop
        self.backdrop = NSVisualEffectView.alloc().initWithFrame_(self.window.contentView().bounds())
        self.backdrop.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable)
        self.backdrop.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
        self.backdrop.setMaterial_(NSVisualEffectMaterialUnderWindowBackground)
        self.backdrop.setState_(NSVisualEffectStateActive)
        self.window.setContentView_(self.backdrop)

        root_view = self.backdrop

        # --- Header Section (Height 80) ---
        # Note: x >= 84 leaves clear space for macOS window traffic lights (close/min/zoom)
        header_height = 80
        win_w = 720
        win_h = 680

        # App Glyph
        self.icon_view = NSImageView.alloc().initWithFrame_(NSMakeRect(84, win_h - 62, 36, 36))
        self.icon_view.setAutoresizingMask_(AppKit.NSViewMaxXMargin | AppKit.NSViewMinYMargin)
        symbol_img = NSImage.imageWithSystemSymbolName_accessibilityDescription_("calendar.badge.clock", "App Icon")
        if symbol_img:
            symbol_img.setTemplate_(False)
            self.icon_view.setImage_(symbol_img)
        root_view.addSubview_(self.icon_view)

        # App Title
        self.lbl_title = NSTextField.alloc().initWithFrame_(NSMakeRect(130, win_h - 46, 220, 22))
        self.lbl_title.setStringValue_("CalendarSync")
        self.lbl_title.setEditable_(False)
        self.lbl_title.setSelectable_(False)
        self.lbl_title.setBezeled_(False)
        self.lbl_title.setDrawsBackground_(False)
        self.lbl_title.setFont_(NSFont.systemFontOfSize_weight_(17.0, NSFontWeightBold))
        self.lbl_title.setAutoresizingMask_(AppKit.NSViewMaxXMargin | AppKit.NSViewMinYMargin)
        root_view.addSubview_(self.lbl_title)

        # Status Pill / Subtitle
        self.lbl_status_pill = NSTextField.alloc().initWithFrame_(NSMakeRect(130, win_h - 66, 300, 18))
        self.lbl_status_pill.setStringValue_("Ready • Idle")
        self.lbl_status_pill.setEditable_(False)
        self.lbl_status_pill.setSelectable_(False)
        self.lbl_status_pill.setBezeled_(False)
        self.lbl_status_pill.setDrawsBackground_(False)
        self.lbl_status_pill.setTextColor_(NSColor.secondaryLabelColor())
        self.lbl_status_pill.setFont_(NSFont.systemFontOfSize_weight_(12.0, NSFontWeightMedium))
        self.lbl_status_pill.setAutoresizingMask_(AppKit.NSViewMaxXMargin | AppKit.NSViewMinYMargin)
        root_view.addSubview_(self.lbl_status_pill)

        # Segmented Control (Configuration vs Activity Logs)
        self.seg_ctrl = NSSegmentedControl.alloc().initWithFrame_(NSMakeRect(win_w - 380, win_h - 58, 240, 28))
        self.seg_ctrl.setSegmentCount_(2)
        self.seg_ctrl.setLabel_forSegment_("Configuration", 0)
        self.seg_ctrl.setLabel_forSegment_("Activity Logs", 1)
        self.seg_ctrl.setSelectedSegment_(0)
        self.seg_ctrl.setTrackingMode_(NSSegmentSwitchTrackingSelectOne)
        self.seg_ctrl.setSegmentStyle_(NSSegmentStyleRounded)
        self.seg_ctrl.setTarget_(self)
        self.seg_ctrl.setAction_("segmentedControlChanged:")
        self.seg_ctrl.setAutoresizingMask_(AppKit.NSViewMinXMargin | AppKit.NSViewMinYMargin)
        root_view.addSubview_(self.seg_ctrl)

        # Prominent Quit App Button in Header
        self.btn_header_quit = NSButton.alloc().initWithFrame_(NSMakeRect(win_w - 124, win_h - 58, 104, 28))
        self.btn_header_quit.setTitle_("Quit App")
        self.btn_header_quit.setBezelStyle_(NSBezelStyleRounded)
        self.btn_header_quit.setTarget_(self)
        self.btn_header_quit.setAction_("quitAppAction:")
        self.btn_header_quit.setToolTip_("Quit CalendarSync completely (⌘Q)")
        self.btn_header_quit.setAutoresizingMask_(AppKit.NSViewMinXMargin | AppKit.NSViewMinYMargin)
        root_view.addSubview_(self.btn_header_quit)

        # Thin separator below header
        sep = NSBox.alloc().initWithFrame_(NSMakeRect(20, win_h - header_height, win_w - 40, 1))
        sep.setBoxType_(AppKit.NSBoxSeparator)
        sep.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewMinYMargin)
        root_view.addSubview_(sep)

        # --- Content Views Container ---
        content_rect = NSMakeRect(0, 0, win_w, win_h - header_height)
        self.container_view = NSView.alloc().initWithFrame_(content_rect)
        self.container_view.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable)
        root_view.addSubview_(self.container_view)

        # Build Tab 1: Configuration View
        self._build_config_view(content_rect)

        # Build Tab 2: Activity Logs View
        self._build_logs_view(content_rect)

        # Show Configuration Tab by default
        self.config_view.setHidden_(False)
        self.logs_view.setHidden_(True)

    def _create_card_box(self, frame) -> NSBox:
        """Create a rounded inset card box conforming to Apple System Settings aesthetic."""
        box = NSBox.alloc().initWithFrame_(frame)
        box.setBoxType_(NSBoxCustom)
        box.setCornerRadius_(10.0)
        box.setBorderWidth_(1.0)
        box.setBorderColor_(NSColor.separatorColor())
        box.setFillColor_(NSColor.controlBackgroundColor().colorWithAlphaComponent_(0.55))
        return box

    def _create_section_label(self, text: str, frame) -> NSTextField:
        """Create an uppercase section label."""
        lbl = NSTextField.alloc().initWithFrame_(frame)
        lbl.setStringValue_(text)
        lbl.setEditable_(False)
        lbl.setSelectable_(False)
        lbl.setBezeled_(False)
        lbl.setDrawsBackground_(False)
        lbl.setTextColor_(NSColor.secondaryLabelColor())
        lbl.setFont_(NSFont.systemFontOfSize_weight_(11.0, NSFontWeightBold))
        return lbl

    # --------------------------------------------------------------------------
    # Configuration Tab UI
    # --------------------------------------------------------------------------
    def _build_config_view(self, frame):
        self.config_view = NSView.alloc().initWithFrame_(frame)
        self.config_view.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable)
        self.container_view.addSubview_(self.config_view)

        card_w = 672
        margin_x = 24

        # Card 1: CALENDARS
        lbl_sec1 = self._create_section_label("CALENDARS", NSMakeRect(margin_x + 6, 560, 200, 16))
        lbl_sec1.setAutoresizingMask_(AppKit.NSViewMaxXMargin)
        self.config_view.addSubview_(lbl_sec1)

        box_cal = self._create_card_box(NSMakeRect(margin_x, 426, card_w, 130))
        box_cal.setAutoresizingMask_(AppKit.NSViewWidthSizable)
        self.config_view.addSubview_(box_cal)

        # Source Calendar
        lbl_src = NSTextField.alloc().initWithFrame_(NSMakeRect(20, 80, 180, 20))
        lbl_src.setStringValue_("Source Calendar")
        lbl_src.setFont_(NSFont.systemFontOfSize_weight_(13.0, NSFontWeightSemibold))
        lbl_src.setEditable_(False)
        lbl_src.setSelectable_(False)
        lbl_src.setBezeled_(False)
        lbl_src.setDrawsBackground_(False)
        lbl_src.setAutoresizingMask_(AppKit.NSViewMaxXMargin)
        box_cal.addSubview_(lbl_src)

        lbl_src_sub = NSTextField.alloc().initWithFrame_(NSMakeRect(20, 62, 200, 16))
        lbl_src_sub.setStringValue_("Calendar to copy events from")
        lbl_src_sub.setFont_(NSFont.systemFontOfSize_(11.0))
        lbl_src_sub.setTextColor_(NSColor.secondaryLabelColor())
        lbl_src_sub.setEditable_(False)
        lbl_src_sub.setSelectable_(False)
        lbl_src_sub.setBezeled_(False)
        lbl_src_sub.setDrawsBackground_(False)
        lbl_src_sub.setAutoresizingMask_(AppKit.NSViewMaxXMargin)
        box_cal.addSubview_(lbl_src_sub)

        self.pop_source = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(230, 72, 330, 26), False)
        self.pop_source.setAutoresizingMask_(AppKit.NSViewWidthSizable)
        box_cal.addSubview_(self.pop_source)

        self.btn_refresh = NSButton.alloc().initWithFrame_(NSMakeRect(570, 72, 85, 26))
        self.btn_refresh.setTitle_("Refresh")
        self.btn_refresh.setBezelStyle_(NSBezelStyleRounded)
        self.btn_refresh.setTarget_(self)
        self.btn_refresh.setAction_("refreshCalendarsAction:")
        self.btn_refresh.setAutoresizingMask_(AppKit.NSViewMinXMargin)
        box_cal.addSubview_(self.btn_refresh)

        # Target Calendar
        lbl_tgt = NSTextField.alloc().initWithFrame_(NSMakeRect(20, 30, 180, 20))
        lbl_tgt.setStringValue_("Target Calendar")
        lbl_tgt.setFont_(NSFont.systemFontOfSize_weight_(13.0, NSFontWeightSemibold))
        lbl_tgt.setEditable_(False)
        lbl_tgt.setSelectable_(False)
        lbl_tgt.setBezeled_(False)
        lbl_tgt.setDrawsBackground_(False)
        lbl_tgt.setAutoresizingMask_(AppKit.NSViewMaxXMargin)
        box_cal.addSubview_(lbl_tgt)

        lbl_tgt_sub = NSTextField.alloc().initWithFrame_(NSMakeRect(20, 12, 200, 16))
        lbl_tgt_sub.setStringValue_("Destination calendar (e.g. Gmail)")
        lbl_tgt_sub.setFont_(NSFont.systemFontOfSize_(11.0))
        lbl_tgt_sub.setTextColor_(NSColor.secondaryLabelColor())
        lbl_tgt_sub.setEditable_(False)
        lbl_tgt_sub.setSelectable_(False)
        lbl_tgt_sub.setBezeled_(False)
        lbl_tgt_sub.setDrawsBackground_(False)
        lbl_tgt_sub.setAutoresizingMask_(AppKit.NSViewMaxXMargin)
        box_cal.addSubview_(lbl_tgt_sub)

        self.pop_target = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(230, 22, 330, 26), False)
        self.pop_target.setAutoresizingMask_(AppKit.NSViewWidthSizable)
        box_cal.addSubview_(self.pop_target)

        # Card 2: SYNC WINDOW & TIMING
        lbl_sec2 = self._create_section_label("SYNC WINDOW & TIMING", NSMakeRect(margin_x + 6, 396, 200, 16))
        lbl_sec2.setAutoresizingMask_(AppKit.NSViewMaxXMargin)
        self.config_view.addSubview_(lbl_sec2)

        box_timing = self._create_card_box(NSMakeRect(margin_x, 252, card_w, 140))
        box_timing.setAutoresizingMask_(AppKit.NSViewWidthSizable)
        self.config_view.addSubview_(box_timing)

        # Past days
        lbl_past = NSTextField.alloc().initWithFrame_(NSMakeRect(20, 94, 200, 18))
        lbl_past.setStringValue_("Rolling Past Window")
        lbl_past.setFont_(NSFont.systemFontOfSize_weight_(13.0, NSFontWeightRegular))
        lbl_past.setEditable_(False)
        lbl_past.setSelectable_(False)
        lbl_past.setBezeled_(False)
        lbl_past.setDrawsBackground_(False)
        box_timing.addSubview_(lbl_past)

        self.tf_past = NSTextField.alloc().initWithFrame_(NSMakeRect(280, 92, 60, 22))
        self.tf_past.setStringValue_("7")
        self.stepper_past = NSStepper.alloc().initWithFrame_(NSMakeRect(345, 92, 19, 22))
        self.stepper_past.setMinValue_(0.0)
        self.stepper_past.setMaxValue_(3650.0)
        self.stepper_past.setDoubleValue_(7.0)
        self.stepper_past.setTarget_(self)
        self.stepper_past.setAction_("stepperPastChanged:")
        box_timing.addSubview_(self.tf_past)
        box_timing.addSubview_(self.stepper_past)

        lbl_unit1 = NSTextField.alloc().initWithFrame_(NSMakeRect(370, 94, 60, 18))
        lbl_unit1.setStringValue_("days")
        lbl_unit1.setFont_(NSFont.systemFontOfSize_(12.0))
        lbl_unit1.setTextColor_(NSColor.secondaryLabelColor())
        lbl_unit1.setEditable_(False)
        lbl_unit1.setSelectable_(False)
        lbl_unit1.setBezeled_(False)
        lbl_unit1.setDrawsBackground_(False)
        box_timing.addSubview_(lbl_unit1)

        # Future days
        lbl_future = NSTextField.alloc().initWithFrame_(NSMakeRect(20, 56, 200, 18))
        lbl_future.setStringValue_("Rolling Future Window")
        lbl_future.setFont_(NSFont.systemFontOfSize_weight_(13.0, NSFontWeightRegular))
        lbl_future.setEditable_(False)
        lbl_future.setSelectable_(False)
        lbl_future.setBezeled_(False)
        lbl_future.setDrawsBackground_(False)
        box_timing.addSubview_(lbl_future)

        self.tf_future = NSTextField.alloc().initWithFrame_(NSMakeRect(280, 54, 60, 22))
        self.tf_future.setStringValue_("30")
        self.stepper_future = NSStepper.alloc().initWithFrame_(NSMakeRect(345, 54, 19, 22))
        self.stepper_future.setMinValue_(1.0)
        self.stepper_future.setMaxValue_(3650.0)
        self.stepper_future.setDoubleValue_(30.0)
        self.stepper_future.setTarget_(self)
        self.stepper_future.setAction_("stepperFutureChanged:")
        box_timing.addSubview_(self.tf_future)
        box_timing.addSubview_(self.stepper_future)

        lbl_unit2 = NSTextField.alloc().initWithFrame_(NSMakeRect(370, 56, 60, 18))
        lbl_unit2.setStringValue_("days")
        lbl_unit2.setFont_(NSFont.systemFontOfSize_(12.0))
        lbl_unit2.setTextColor_(NSColor.secondaryLabelColor())
        lbl_unit2.setEditable_(False)
        lbl_unit2.setSelectable_(False)
        lbl_unit2.setBezeled_(False)
        lbl_unit2.setDrawsBackground_(False)
        box_timing.addSubview_(lbl_unit2)

        # Sync interval
        lbl_interval = NSTextField.alloc().initWithFrame_(NSMakeRect(20, 18, 200, 18))
        lbl_interval.setStringValue_("Background Sync Interval")
        lbl_interval.setFont_(NSFont.systemFontOfSize_weight_(13.0, NSFontWeightRegular))
        lbl_interval.setEditable_(False)
        lbl_interval.setSelectable_(False)
        lbl_interval.setBezeled_(False)
        lbl_interval.setDrawsBackground_(False)
        box_timing.addSubview_(lbl_interval)

        self.tf_interval = NSTextField.alloc().initWithFrame_(NSMakeRect(280, 16, 60, 22))
        self.tf_interval.setStringValue_("15")
        self.stepper_interval = NSStepper.alloc().initWithFrame_(NSMakeRect(345, 16, 19, 22))
        self.stepper_interval.setMinValue_(1.0)
        self.stepper_interval.setMaxValue_(1440.0)
        self.stepper_interval.setDoubleValue_(15.0)
        self.stepper_interval.setTarget_(self)
        self.stepper_interval.setAction_("stepperIntervalChanged:")
        box_timing.addSubview_(self.tf_interval)
        box_timing.addSubview_(self.stepper_interval)

        lbl_unit3 = NSTextField.alloc().initWithFrame_(NSMakeRect(370, 18, 60, 18))
        lbl_unit3.setStringValue_("minutes")
        lbl_unit3.setFont_(NSFont.systemFontOfSize_(12.0))
        lbl_unit3.setTextColor_(NSColor.secondaryLabelColor())
        lbl_unit3.setEditable_(False)
        lbl_unit3.setSelectable_(False)
        lbl_unit3.setBezeled_(False)
        lbl_unit3.setDrawsBackground_(False)
        box_timing.addSubview_(lbl_unit3)

        # Card 3: ACTIONS & PREFERENCES
        lbl_sec3 = self._create_section_label("ACTIONS & PREFERENCES", NSMakeRect(margin_x + 6, 224, 220, 16))
        lbl_sec3.setAutoresizingMask_(AppKit.NSViewMaxXMargin)
        self.config_view.addSubview_(lbl_sec3)

        box_actions = self._create_card_box(NSMakeRect(margin_x, 44, card_w, 176))
        box_actions.setAutoresizingMask_(AppKit.NSViewWidthSizable)
        self.config_view.addSubview_(box_actions)

        # Row 1: Primary Controls
        self.btn_save = NSButton.alloc().initWithFrame_(NSMakeRect(20, 132, 160, 32))
        self.btn_save.setTitle_("Save Configuration")
        self.btn_save.setBezelStyle_(NSBezelStyleRounded)
        self.btn_save.setKeyEquivalent_("\r")
        self.btn_save.setTarget_(self)
        self.btn_save.setAction_("saveConfigAction:")
        box_actions.addSubview_(self.btn_save)

        self.btn_sync_now = NSButton.alloc().initWithFrame_(NSMakeRect(190, 132, 120, 32))
        self.btn_sync_now.setTitle_("Sync Now")
        self.btn_sync_now.setBezelStyle_(NSBezelStyleRounded)
        self.btn_sync_now.setTarget_(self)
        self.btn_sync_now.setAction_("syncNowAction:")
        box_actions.addSubview_(self.btn_sync_now)

        self.btn_dry_run = NSButton.alloc().initWithFrame_(NSMakeRect(320, 132, 150, 32))
        self.btn_dry_run.setTitle_("Dry Run Preview")
        self.btn_dry_run.setBezelStyle_(NSBezelStyleRounded)
        self.btn_dry_run.setTarget_(self)
        self.btn_dry_run.setAction_("dryRunAction:")
        box_actions.addSubview_(self.btn_dry_run)

        # Divider 1 inside card
        div_act1 = NSBox.alloc().initWithFrame_(NSMakeRect(20, 120, card_w - 40, 1))
        div_act1.setBoxType_(AppKit.NSBoxSeparator)
        div_act1.setAutoresizingMask_(AppKit.NSViewWidthSizable)
        box_actions.addSubview_(div_act1)

        # Row 2: Maintenance Controls
        self.btn_reset_state = NSButton.alloc().initWithFrame_(NSMakeRect(20, 78, 160, 28))
        self.btn_reset_state.setTitle_("Reset Sync State...")
        self.btn_reset_state.setBezelStyle_(NSBezelStyleRounded)
        self.btn_reset_state.setTarget_(self)
        self.btn_reset_state.setAction_("resetStateAction:")
        box_actions.addSubview_(self.btn_reset_state)

        lbl_reset_desc = NSTextField.alloc().initWithFrame_(NSMakeRect(22, 54, 260, 20))
        lbl_reset_desc.setStringValue_("Clears mapping DB to force fresh re-scan.")
        lbl_reset_desc.setFont_(NSFont.systemFontOfSize_(10.5))
        lbl_reset_desc.setTextColor_(NSColor.secondaryLabelColor())
        lbl_reset_desc.setEditable_(False)
        lbl_reset_desc.setSelectable_(False)
        lbl_reset_desc.setBezeled_(False)
        lbl_reset_desc.setDrawsBackground_(False)
        box_actions.addSubview_(lbl_reset_desc)

        self.btn_clear_target = NSButton.alloc().initWithFrame_(NSMakeRect(300, 78, 180, 28))
        self.btn_clear_target.setTitle_("Clear Target Calendar...")
        self.btn_clear_target.setBezelStyle_(NSBezelStyleRounded)
        self.btn_clear_target.setTarget_(self)
        self.btn_clear_target.setAction_("clearTargetAction:")
        box_actions.addSubview_(self.btn_clear_target)

        lbl_clear_desc = NSTextField.alloc().initWithFrame_(NSMakeRect(302, 54, 330, 20))
        lbl_clear_desc.setStringValue_("Deletes all events from target calendar (destructive).")
        lbl_clear_desc.setFont_(NSFont.systemFontOfSize_(10.5))
        lbl_clear_desc.setTextColor_(NSColor.secondaryLabelColor())
        lbl_clear_desc.setEditable_(False)
        lbl_clear_desc.setSelectable_(False)
        lbl_clear_desc.setBezeled_(False)
        lbl_clear_desc.setDrawsBackground_(False)
        box_actions.addSubview_(lbl_clear_desc)

        # Divider 2 inside card
        div_act2 = NSBox.alloc().initWithFrame_(NSMakeRect(20, 44, card_w - 40, 1))
        div_act2.setBoxType_(AppKit.NSBoxSeparator)
        div_act2.setAutoresizingMask_(AppKit.NSViewWidthSizable)
        box_actions.addSubview_(div_act2)

        # Row 3: App Preferences Checkboxes
        self.chk_menu_bar_only = NSButton.alloc().initWithFrame_(NSMakeRect(20, 14, 260, 22))
        self.chk_menu_bar_only.setButtonType_(AppKit.NSButtonTypeSwitch)
        self.chk_menu_bar_only.setTitle_("Run in Menu Bar only (hide from Dock)")
        self.chk_menu_bar_only.setState_(NSControlStateValueOn)
        box_actions.addSubview_(self.chk_menu_bar_only)

        self.chk_start_at_login = NSButton.alloc().initWithFrame_(NSMakeRect(300, 14, 260, 22))
        self.chk_start_at_login.setButtonType_(AppKit.NSButtonTypeSwitch)
        self.chk_start_at_login.setTitle_("Start CalendarSync at Login")
        self.chk_start_at_login.setState_(NSControlStateValueOn if is_start_at_login_enabled() else NSControlStateValueOff)
        box_actions.addSubview_(self.chk_start_at_login)

        # Footer Status Label & Quit Button
        self.lbl_footer = NSTextField.alloc().initWithFrame_(NSMakeRect(margin_x + 6, 16, card_w - 150, 20))
        self.lbl_footer.setStringValue_("In-app scheduler: Active  •  Auto-syncs every 15 minutes")
        self.lbl_footer.setFont_(NSFont.systemFontOfSize_weight_(11.5, NSFontWeightRegular))
        self.lbl_footer.setTextColor_(NSColor.secondaryLabelColor())
        self.lbl_footer.setEditable_(False)
        self.lbl_footer.setSelectable_(False)
        self.lbl_footer.setBezeled_(False)
        self.lbl_footer.setDrawsBackground_(False)
        self.lbl_footer.setAutoresizingMask_(AppKit.NSViewWidthSizable)
        self.config_view.addSubview_(self.lbl_footer)

        self.btn_quit_footer = NSButton.alloc().initWithFrame_(NSMakeRect(margin_x + card_w - 150, 12, 150, 28))
        self.btn_quit_footer.setTitle_("Quit CalendarSync")
        self.btn_quit_footer.setBezelStyle_(NSBezelStyleRounded)
        self.btn_quit_footer.setTarget_(self)
        self.btn_quit_footer.setAction_("quitAppAction:")
        self.btn_quit_footer.setToolTip_("Quit CalendarSync completely (⌘Q)")
        self.btn_quit_footer.setAutoresizingMask_(AppKit.NSViewMinXMargin)
        self.config_view.addSubview_(self.btn_quit_footer)

    # --------------------------------------------------------------------------
    # Activity Logs Tab UI
    # --------------------------------------------------------------------------
    def _build_logs_view(self, frame):
        self.logs_view = NSView.alloc().initWithFrame_(frame)
        self.logs_view.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable)
        self.container_view.addSubview_(self.logs_view)

        card_w = 672
        margin_x = 24

        # Action Bar (Search field, Auto-scroll, Copy, Clear, Open Finder)
        bar_y = 560
        self.search_field = NSSearchField.alloc().initWithFrame_(NSMakeRect(margin_x, bar_y, 240, 26))
        self.search_field.setPlaceholderString_("Filter logs (e.g. [CREATED])...")
        self.search_field.setTarget_(self)
        self.search_field.setAction_("searchFieldChanged:")
        self.search_field.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewMinYMargin)
        self.logs_view.addSubview_(self.search_field)

        self.chk_autoscroll = NSButton.alloc().initWithFrame_(NSMakeRect(margin_x + 250, bar_y + 3, 100, 20))
        self.chk_autoscroll.setButtonType_(AppKit.NSButtonTypeSwitch)
        self.chk_autoscroll.setTitle_("Auto-scroll")
        self.chk_autoscroll.setState_(NSControlStateValueOn)
        self.chk_autoscroll.setAutoresizingMask_(AppKit.NSViewMinXMargin | AppKit.NSViewMinYMargin)
        self.logs_view.addSubview_(self.chk_autoscroll)

        self.btn_copy_logs = NSButton.alloc().initWithFrame_(NSMakeRect(margin_x + 360, bar_y, 80, 26))
        self.btn_copy_logs.setTitle_("Copy All")
        self.btn_copy_logs.setBezelStyle_(NSBezelStyleRounded)
        self.btn_copy_logs.setTarget_(self)
        self.btn_copy_logs.setAction_("copyLogsAction:")
        self.btn_copy_logs.setAutoresizingMask_(AppKit.NSViewMinXMargin | AppKit.NSViewMinYMargin)
        self.logs_view.addSubview_(self.btn_copy_logs)

        self.btn_clear_logs = NSButton.alloc().initWithFrame_(NSMakeRect(margin_x + 450, bar_y, 90, 26))
        self.btn_clear_logs.setTitle_("Clear Logs")
        self.btn_clear_logs.setBezelStyle_(NSBezelStyleRounded)
        self.btn_clear_logs.setTarget_(self)
        self.btn_clear_logs.setAction_("clearLogsAction:")
        self.btn_clear_logs.setAutoresizingMask_(AppKit.NSViewMinXMargin | AppKit.NSViewMinYMargin)
        self.logs_view.addSubview_(self.btn_clear_logs)

        self.btn_finder = NSButton.alloc().initWithFrame_(NSMakeRect(margin_x + 550, bar_y, 115, 26))
        self.btn_finder.setTitle_("Open in Finder")
        self.btn_finder.setBezelStyle_(NSBezelStyleRounded)
        self.btn_finder.setTarget_(self)
        self.btn_finder.setAction_("openLogsInFinderAction:")
        self.btn_finder.setAutoresizingMask_(AppKit.NSViewMinXMargin | AppKit.NSViewMinYMargin)
        self.logs_view.addSubview_(self.btn_finder)

        # Log ScrollView & TextView
        scroll_rect = NSMakeRect(margin_x, 20, card_w, 530)
        self.log_scroll_view = NSScrollView.alloc().initWithFrame_(scroll_rect)
        self.log_scroll_view.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable)
        self.log_scroll_view.setHasVerticalScroller_(True)
        self.log_scroll_view.setHasHorizontalScroller_(False)
        self.log_scroll_view.setBorderType_(AppKit.NSBezelBorder)

        self.log_text_view = NSTextView.alloc().initWithFrame_(
            NSMakeRect(0, 0, scroll_rect.size.width - 15, scroll_rect.size.height)
        )
        self.log_text_view.setEditable_(False)
        self.log_text_view.setSelectable_(True)
        self.log_text_view.setFont_(NSFont.monospacedSystemFontOfSize_weight_(11.5, NSFontWeightRegular))
        self.log_text_view.setBackgroundColor_(NSColor.controlBackgroundColor().colorWithAlphaComponent_(0.7))
        self.log_text_view.setMinSize_(NSMakeSize(0.0, scroll_rect.size.height))
        self.log_text_view.setMaxSize_(NSMakeSize(float('inf'), float('inf')))
        self.log_text_view.setVerticallyResizable_(True)
        self.log_text_view.setHorizontallyResizable_(False)
        self.log_text_view.setAutoresizingMask_(AppKit.NSViewWidthSizable)
        self.log_text_view.textContainer().setContainerSize_(NSMakeSize(scroll_rect.size.width - 15, float('inf')))
        self.log_text_view.textContainer().setWidthTracksTextView_(True)
        self.log_scroll_view.setDocumentView_(self.log_text_view)

        self.logs_view.addSubview_(self.log_scroll_view)

    # --------------------------------------------------------------------------
    # Public Controller API
    # --------------------------------------------------------------------------
    def show_window(self, tab_index: Optional[int] = None):
        """Bring window to foreground, optionally switching to a specific tab."""
        if tab_index is not None:
            self.seg_ctrl.setSelectedSegment_(tab_index)
            self._switch_tab(tab_index)

        self.window.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)
        self.load_configuration_into_ui()
        self.reload_logs()

    def set_scheduler(self, scheduler: SyncScheduler):
        self.scheduler = scheduler

    def load_configuration_into_ui(self):
        """Populate UI fields from config.yaml and available calendars."""
        cfg = load_app_config()

        past = cfg.get("rolling_days_past", 7)
        future = cfg.get("rolling_days_future", 30)
        interval = cfg.get("sync_interval_minutes", 15)
        menu_bar_only = cfg.get("run_in_menu_bar_only", True)

        self.tf_past.setStringValue_(str(past))
        self.stepper_past.setDoubleValue_(float(past))

        self.tf_future.setStringValue_(str(future))
        self.stepper_future.setDoubleValue_(float(future))

        self.tf_interval.setStringValue_(str(interval))
        self.stepper_interval.setDoubleValue_(float(interval))

        self.chk_menu_bar_only.setState_(NSControlStateValueOn if menu_bar_only else NSControlStateValueOff)
        self.chk_start_at_login.setState_(NSControlStateValueOn if is_start_at_login_enabled() else NSControlStateValueOff)

        self.refresh_calendars_list()

    def refresh_calendars_list(self, background: bool = True):
        """Query EventKit and Microsoft Outlook for available calendars and populate source & target popups."""
        self.lbl_status_pill.setStringValue_("Scanning calendars...")
        if background:
            threading.Thread(target=self._async_fetch_calendars, daemon=True).start()
        else:
            self._async_fetch_calendars()

    def _async_fetch_calendars(self):
        all_cals = []
        errors = []

        # 1. Query Microsoft Outlook Calendars (fast)
        try:
            from outlook_calendar import OutlookCalendarClient
            out_client = OutlookCalendarClient()
            if out_client.is_available():
                out_cals = out_client.get_calendars(include_event_counts=True)
                all_cals.extend(out_cals)
        except Exception as e:
            errors.append(f"Outlook: {e}")

        # 2. Query EventKit macOS Calendars
        try:
            client = MacCalendarClient()
            mac_cals = client.get_calendars(include_event_counts=True)
            all_cals.extend(mac_cals)
        except Exception as e:
            errors.append(f"Mac Calendar: {e}")

        MainThreadDispatcher.run_on_main(self._update_calendar_popups_ui, all_cals, errors)

    def _update_calendar_popups_ui(self, all_cals: List[Dict[str, Any]], errors: List[str]):
        cfg = load_app_config()
        saved_src_id = cfg.get("source_calendar_id", "")
        saved_src_name = cfg.get("source_calendar_name", "")
        saved_tgt_id = cfg.get("target_calendar_id", "")
        saved_tgt_name = cfg.get("target_calendar_name", "")

        self.cached_calendars = all_cals
        if errors and not all_cals:
            err_summary = "; ".join(errors)
            self.lbl_status_pill.setStringValue_(f"Error: {err_summary[:60]}")
        elif errors and all_cals:
            self.lbl_status_pill.setStringValue_(f"✓ {len(all_cals)} calendars ready (Note: {str(errors[0])[:35]})")
        else:
            self.lbl_status_pill.setStringValue_(f"✓ {len(all_cals)} calendars ready")

        self.pop_source.removeAllItems()
        self.pop_target.removeAllItems()

        if not self.cached_calendars:
            src_title = f"{saved_src_name} [ID: {saved_src_id[:12]}...]" if saved_src_id else (saved_src_name or "No Calendars Detected")
            tgt_title = f"{saved_tgt_name} [ID: {saved_tgt_id[:12]}...]" if saved_tgt_id else (saved_tgt_name or "No Calendars Detected")
            
            self.pop_source.addItemWithTitle_(src_title)
            if saved_src_id:
                self.pop_source.lastItem().setRepresentedObject_(saved_src_id)

            self.pop_target.addItemWithTitle_(tgt_title)
            if saved_tgt_id:
                self.pop_target.lastItem().setRepresentedObject_(saved_tgt_id)
            return

        src_found = False
        tgt_found = False

        for cal in self.cached_calendars:
            count = cal.get("event_count_1yr")
            count_str = f" — {count} events" if count is not None else ""
            provider_tag = "[Outlook]" if cal.get("provider") == "outlook" else "[Mac/Google]"
            title_str = f"{provider_tag} {cal['title']} ({cal['source']}){count_str}"

            self.pop_source.addItemWithTitle_(title_str)
            item_src = self.pop_source.lastItem()
            item_src.setRepresentedObject_(cal["identifier"])

            self.pop_target.addItemWithTitle_(title_str)
            item_tgt = self.pop_target.lastItem()
            item_tgt.setRepresentedObject_(cal["identifier"])

            if cal["identifier"] == saved_src_id or cal.get("raw_id") == saved_src_id:
                self.pop_source.selectItem_(item_src)
                src_found = True
            if cal["identifier"] == saved_tgt_id or cal.get("raw_id") == saved_tgt_id:
                self.pop_target.selectItem_(item_tgt)
                tgt_found = True

        # Ensure currently saved calendar is represented if not returned by scan
        if saved_src_id and not src_found:
            saved_title = f"{saved_src_name or 'Current Source'} ({saved_src_id[:16]}...) [Configured]"
            self.pop_source.insertItemWithTitle_atIndex_(saved_title, 0)
            item = self.pop_source.itemAtIndex_(0)
            item.setRepresentedObject_(saved_src_id)
            self.pop_source.selectItem_(item)

        if saved_tgt_id and not tgt_found:
            saved_title = f"{saved_tgt_name or 'Current Target'} ({saved_tgt_id[:16]}...) [Configured]"
            self.pop_target.insertItemWithTitle_atIndex_(saved_title, 0)
            item = self.pop_target.itemAtIndex_(0)
            item.setRepresentedObject_(saved_tgt_id)
            self.pop_target.selectItem_(item)

    def reload_logs(self):
        """Read and format the activity log."""
        log_path = get_app_data_path(SYNC_LOG_FILE)
        raw_text = ""
        if os.path.exists(log_path):
            try:
                with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                    # Show up to 1000 lines for smoothness
                    raw_text = "".join(lines[-1000:])
            except Exception as e:
                raw_text = f"Error reading log file: {e}"
        else:
            raw_text = "No sync activity recorded yet. Run 'Sync Now' or 'Dry Run Preview' to start."

        filter_q = self.search_field.stringValue()
        attributed = colorize_log_text(raw_text, filter_query=filter_q)
        self.log_text_view.textStorage().setAttributedString_(attributed)

        if self.chk_autoscroll.state() == NSControlStateValueOn:
            length = self.log_text_view.textStorage().length()
            self.log_text_view.scrollRangeToVisible_(NSMakeRange(length, 0))

    def update_sync_ui_state(self, is_syncing: bool, stats: Optional[dict] = None, error: Optional[str] = None, dry_run: bool = False):
        """Update window indicators when sync starts or finishes."""
        if is_syncing:
            mode = "Dry Run in progress..." if dry_run else "Syncing..."
            self.lbl_status_pill.setStringValue_(mode)
            self.lbl_status_pill.setTextColor_(NSColor.systemOrangeColor() if dry_run else NSColor.systemBlueColor())
            self.btn_sync_now.setEnabled_(False)
            self.btn_dry_run.setEnabled_(False)
        else:
            self.btn_sync_now.setEnabled_(True)
            self.btn_dry_run.setEnabled_(True)
            now_str = datetime.now().strftime("%H:%M:%S")
            if error:
                self.lbl_status_pill.setStringValue_(f"Sync Failed: {error[:30]}")
                self.lbl_status_pill.setTextColor_(NSColor.systemRedColor())
            elif stats:
                prefix = "[Dry Run] " if dry_run else ""
                c = stats.get("created", 0)
                u = stats.get("updated", 0)
                d = stats.get("deleted", 0)
                self.lbl_status_pill.setStringValue_(f"{prefix}Last Sync: {now_str} (+{c}, ~{u}, -{d})")
                self.lbl_status_pill.setTextColor_(NSColor.systemGreenColor())
            else:
                self.lbl_status_pill.setStringValue_(f"Ready • Idle")
                self.lbl_status_pill.setTextColor_(NSColor.secondaryLabelColor())

        self.reload_logs()

    # --------------------------------------------------------------------------
    # Action Selectors
    # --------------------------------------------------------------------------
    def segmentedControlChanged_(self, sender):
        idx = sender.selectedSegment()
        self._switch_tab(idx)

    def _switch_tab(self, idx: int):
        if idx == 0:
            self.config_view.setHidden_(False)
            self.logs_view.setHidden_(True)
        else:
            self.config_view.setHidden_(True)
            self.logs_view.setHidden_(False)
            self.reload_logs()

    def stepperPastChanged_(self, sender):
        val = int(sender.doubleValue())
        self.tf_past.setStringValue_(str(val))

    def stepperFutureChanged_(self, sender):
        val = int(sender.doubleValue())
        self.tf_future.setStringValue_(str(val))

    def stepperIntervalChanged_(self, sender):
        val = int(sender.doubleValue())
        self.tf_interval.setStringValue_(str(val))

    def refreshCalendarsAction_(self, sender):
        self.refresh_calendars_list()

    def saveConfigAction_(self, sender):
        """Save form values to config.yaml and notify scheduler."""
        try:
            src_item = self.pop_source.selectedItem()
            tgt_item = self.pop_target.selectedItem()

            src_id = src_item.representedObject() if src_item else ""
            tgt_id = tgt_item.representedObject() if tgt_item else ""

            # If representedObject is None, check cached calendars by index
            if not src_id and self.cached_calendars:
                idx = self.pop_source.indexOfSelectedItem()
                if 0 <= idx < len(self.cached_calendars):
                    src_id = self.cached_calendars[idx]["identifier"]

            if not tgt_id and self.cached_calendars:
                idx = self.pop_target.indexOfSelectedItem()
                if 0 <= idx < len(self.cached_calendars):
                    tgt_id = self.cached_calendars[idx]["identifier"]

            if src_id and tgt_id and src_id == tgt_id:
                alert = NSAlert.alloc().init()
                alert.setMessageText_("Invalid Calendar Selection")
                alert.setInformativeText_("Source and Target calendars cannot be the same. Please choose different calendars.")
                alert.setAlertStyle_(NSAlertStyleCritical)
                alert.runModal()
                return

            # Resolve names & accounts
            src_name = ""
            src_acc = ""
            tgt_name = ""
            tgt_acc = ""
            for c in self.cached_calendars:
                if c["identifier"] == src_id:
                    src_name = c["title"]
                    src_acc = c["source"]
                if c["identifier"] == tgt_id:
                    tgt_name = c["title"]
                    tgt_acc = c["source"]

            past_val = int(self.tf_past.stringValue() or "7")
            future_val = int(self.tf_future.stringValue() or "30")
            interval_val = int(self.tf_interval.stringValue() or "15")

            menu_bar_only = bool(self.chk_menu_bar_only.state() == NSControlStateValueOn)
            start_login = bool(self.chk_start_at_login.state() == NSControlStateValueOn)
            set_start_at_login(start_login)

            if menu_bar_only:
                NSApp.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
            else:
                NSApp.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)

            cfg = load_app_config()
            cfg.update({
                "source_calendar_id": src_id or cfg.get("source_calendar_id", ""),
                "source_calendar_name": src_name or cfg.get("source_calendar_name", ""),
                "source_calendar_account": src_acc or cfg.get("source_calendar_account", ""),
                "target_calendar_id": tgt_id or cfg.get("target_calendar_id", ""),
                "target_calendar_name": tgt_name or cfg.get("target_calendar_name", ""),
                "target_calendar_account": tgt_acc or cfg.get("target_calendar_account", ""),
                "rolling_days_past": past_val,
                "rolling_days_future": future_val,
                "sync_interval_minutes": interval_val,
                "run_in_menu_bar_only": menu_bar_only,
            })
            save_app_config(cfg)

            if self.scheduler:
                self.scheduler.update_interval_minutes(interval_val)

            self.lbl_footer.setStringValue_(
                f"Configuration saved! In-app scheduler set to sync every {interval_val} minutes."
            )
            self.lbl_footer.setTextColor_(NSColor.systemGreenColor())

            # Brief alert banner
            alert = NSAlert.alloc().init()
            alert.setMessageText_("Configuration Saved")
            alert.setInformativeText_(
                f"Settings saved successfully.\nSync interval: Every {interval_val} minutes."
            )
            alert.setAlertStyle_(NSAlertStyleInformational)
            alert.addButtonWithTitle_("OK")
            alert.beginSheetModalForWindow_completionHandler_(self.window, None)

        except Exception as e:
            alert = NSAlert.alloc().init()
            alert.setMessageText_("Save Failed")
            alert.setInformativeText_(str(e))
            alert.setAlertStyle_(NSAlertStyleCritical)
            alert.runModal()

    def syncNowAction_(self, sender):
        if self.scheduler:
            self.scheduler.trigger_sync(dry_run=False, is_manual=True)

    def dryRunAction_(self, sender):
        if self.scheduler:
            self.scheduler.trigger_sync(dry_run=True, is_manual=True)
            # Switch to Activity Logs tab to see preview
            self.seg_ctrl.setSelectedSegment_(1)
            self._switch_tab(1)

    def resetStateAction_(self, sender):
        """Reset the local SQLite mapping database after confirmation."""
        alert = NSAlert.alloc().init()
        alert.setMessageText_("Reset Sync State Database?")
        alert.setInformativeText_(
            "This will remove the local sync_state.db file. On the next sync cycle, "
            "CalendarSync will perform a fresh re-scan of all events in both calendars."
        )
        alert.setAlertStyle_(NSAlertStyleWarning)
        alert.addButtonWithTitle_("Reset State")
        alert.addButtonWithTitle_("Cancel")

        res = alert.runModal()
        if res == NSAlertFirstButtonReturn:
            cfg = load_app_config()
            db_path = get_app_data_path(cfg.get("state_db_file", "sync_state.db"))
            if os.path.exists(db_path):
                try:
                    os.remove(db_path)
                    self.lbl_footer.setStringValue_("Sync state store cleared successfully.")
                    self.lbl_footer.setTextColor_(NSColor.systemGreenColor())
                except Exception as e:
                    self.lbl_footer.setStringValue_(f"Error removing state db: {e}")
                    self.lbl_footer.setTextColor_(NSColor.systemRedColor())
            else:
                self.lbl_footer.setStringValue_("No sync state db file found.")

    def clearTargetAction_(self, sender):
        """Delete all events from the target calendar after explicit user confirmation."""
        cfg = load_app_config()
        tgt_name = cfg.get("target_calendar_name", "Target Calendar")
        tgt_id = cfg.get("target_calendar_id", "")

        if not tgt_id:
            alert = NSAlert.alloc().init()
            alert.setMessageText_("No Target Calendar Configured")
            alert.setInformativeText_("Please select and save a Target Calendar first.")
            alert.runModal()
            return

        alert = NSAlert.alloc().init()
        alert.setMessageText_(f"Permanently Clear '{tgt_name}'?")
        alert.setInformativeText_(
            f"WARNING: This will permanently delete ALL events inside target calendar '{tgt_name}' "
            f"and reset the sync database. This action CANNOT be undone."
        )
        alert.setAlertStyle_(NSAlertStyleCritical)
        alert.addButtonWithTitle_("Delete All Events")
        alert.addButtonWithTitle_("Cancel")

        res = alert.runModal()
        if res == NSAlertFirstButtonReturn:
            try:
                client = MacCalendarClient()
                db_path = get_app_data_path(cfg.get("state_db_file", "sync_state.db"))
                store = SyncStateStore(db_path)
                engine = SyncEngine(
                    mac_client=client,
                    state_store=store,
                    source_calendar_id=cfg.get("source_calendar_id", ""),
                    target_calendar_id=tgt_id,
                    target_calendar_name=tgt_name
                )
                deleted = engine.clear_target_calendar()
                self.reload_logs()

                done_alert = NSAlert.alloc().init()
                done_alert.setMessageText_("Target Calendar Cleared")
                done_alert.setInformativeText_(f"Deleted {deleted} events from '{tgt_name}'.")
                done_alert.setAlertStyle_(NSAlertStyleInformational)
                done_alert.runModal()
            except Exception as e:
                err_alert = NSAlert.alloc().init()
                err_alert.setMessageText_("Clear Failed")
                err_alert.setInformativeText_(str(e))
                err_alert.setAlertStyle_(NSAlertStyleCritical)
                err_alert.runModal()

    def searchFieldChanged_(self, sender):
        self.reload_logs()

    def copyLogsAction_(self, sender):
        content = self.log_text_view.string()
        if content:
            pb = NSPasteboard.generalPasteboard()
            pb.clearContents()
            pb.setString_forType_(content, NSPasteboardTypeString)
            self.lbl_footer.setStringValue_("Copied activity logs to clipboard.")

    def clearLogsAction_(self, sender):
        log_path = get_app_data_path(SYNC_LOG_FILE)
        if os.path.exists(log_path):
            with open(log_path, "w") as f:
                f.write(f"=== Logs Cleared at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        self.reload_logs()

    def openLogsInFinderAction_(self, sender):
        log_path = get_app_data_path(SYNC_LOG_FILE)
        if not os.path.exists(log_path):
            with open(log_path, "w") as f:
                f.write(f"=== CalendarSync Log Created {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        NSWorkspace.sharedWorkspace().selectFile_inFileViewerRootedAtPath_(log_path, "")

    def quitAppAction_(self, sender):
        """Fully quit CalendarSync application."""
        if hasattr(self, "scheduler") and self.scheduler:
            self.scheduler.stop()
        if self.window:
            self.window.orderOut_(None)
        NSApp.terminate_(None)
        os._exit(0)

    def windowShouldClose_(self, sender):
        """Handle window close ('X' button)."""
        cfg = load_app_config()
        if not cfg.get("run_in_menu_bar_only", True):
            if hasattr(self, "scheduler") and self.scheduler:
                self.scheduler.stop()
            NSApp.terminate_(None)
            os._exit(0)
            return True
        self.window.orderOut_(None)
        return False


# ==============================================================================
# Recent Log Helpers for Status Menu
# ==============================================================================
def fetch_recent_log_entries(limit: int = 3) -> List[str]:
    """Return the latest N entries from sync_events.log or sync.log."""
    entries = []
    events_path = get_app_data_path(SYNC_LOG_FILE)
    if os.path.exists(events_path):
        try:
            with open(events_path, "r", encoding="utf-8", errors="replace") as f:
                for line in reversed(f.readlines()):
                    line = line.strip()
                    if not line or line.startswith("===") or line.startswith("---") or line.startswith("Detailed audit log"):
                        continue
                    compact = " ".join(line.split())
                    entries.append(compact)
                    if len(entries) >= limit:
                        break
        except Exception:
            pass

    if not entries:
        sync_log_path = get_app_data_path("sync.log")
        if os.path.exists(sync_log_path):
            try:
                with open(sync_log_path, "r", encoding="utf-8", errors="replace") as f:
                    for line in reversed(f.readlines()):
                        line = line.strip()
                        if not line or line.startswith("===") or line.startswith("---") or line.startswith("Detailed audit log"):
                            continue
                        compact = " ".join(line.split())
                        entries.append(compact)
                        if len(entries) >= limit:
                            break
            except Exception:
                pass

    return entries


def format_menu_log_entry(raw_entry: str, max_len: int = 50) -> str:
    """Format a raw log line with clean icon indicator and length truncation."""
    prefix = "• "
    if "[CREATED]" in raw_entry:
        prefix = "🟢 "
    elif "[UPDATED]" in raw_entry:
        prefix = "🟡 "
    elif "[DELETED]" in raw_entry:
        prefix = "🔴 "
    elif "[UNCHANGED]" in raw_entry:
        prefix = "⚪️ "
    elif "error" in raw_entry.lower():
        prefix = "⚠️ "

    text = raw_entry
    if len(text) > max_len:
        text = text[:max_len - 3] + "..."
    return f"{prefix}{text}"


# ==============================================================================
# Menu Bar Controller (NSStatusItem)
# ==============================================================================
class StatusItemController(NSObject):
    """Manages the menu bar icon, status indicator, and context dropdown menu."""

    def init(self):
        self = objc.super(StatusItemController, self).init()
        if self is None:
            return None

        self.status_item = None
        self.window_controller: Optional[MainWindowController] = None
        self.scheduler: Optional[SyncScheduler] = None

        self._icon_idle = None
        self._icon_syncing = None
        self.recent_log_items: List[NSMenuItem] = []

        self._setup_status_item()
        return self

    def set_dependencies(self, window_ctrl: MainWindowController, scheduler: SyncScheduler):
        self.window_controller = window_ctrl
        self.scheduler = scheduler

    def _setup_status_item(self):
        self.status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSSquareStatusItemLength)
        self.status_item.setVisible_(True)

        # Load Apple SF Symbols
        self._icon_idle = NSImage.imageWithSystemSymbolName_accessibilityDescription_("calendar.badge.clock", "CalendarSync")
        if self._icon_idle:
            self._icon_idle.setTemplate_(True)

        self._icon_syncing = NSImage.imageWithSystemSymbolName_accessibilityDescription_("arrow.triangle.2.circlepath", "Syncing...")
        if self._icon_syncing:
            self._icon_syncing.setTemplate_(True)

        button = self.status_item.button()
        if self._icon_idle:
            button.setImage_(self._icon_idle)
        else:
            button.setTitle_("📅")
        button.setToolTip_("CalendarSync")
        button.setTarget_(self)
        button.setAction_("statusItemClicked:")

        # Build dropdown menu
        self.menu = NSMenu.alloc().init()

        # Status Headline (Clickable -> opens logs)
        self.item_status = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "CalendarSync • Status: Ready", "menuViewLogsAction:", ""
        )
        self.item_status.setTarget_(self)
        self.menu.addItem_(self.item_status)

        self.menu.addItem_(NSMenuItem.separatorItem())

        # Sync Now (⌘S)
        self.item_sync_now = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Sync Now", "menuSyncNowAction:", "s")
        self.item_sync_now.setKeyEquivalentModifierMask_(NSEventModifierFlagCommand)
        self.item_sync_now.setTarget_(self)
        self.menu.addItem_(self.item_sync_now)

        # View Logs (⌘L)
        self.item_logs = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("View Activity Logs...", "menuViewLogsAction:", "l")
        self.item_logs.setKeyEquivalentModifierMask_(NSEventModifierFlagCommand)
        self.item_logs.setTarget_(self)
        self.menu.addItem_(self.item_logs)

        # Open Settings (⌘,)
        self.item_settings = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Configuration / Settings...", "menuOpenSettingsAction:", ",")
        self.item_settings.setKeyEquivalentModifierMask_(NSEventModifierFlagCommand)
        self.item_settings.setTarget_(self)
        self.menu.addItem_(self.item_settings)

        # Latest 3 Log Entries Section
        self.menu.addItem_(NSMenuItem.separatorItem())
        self.item_recent_header = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Recent Activity Logs:", "", "")
        self.item_recent_header.setEnabled_(False)
        self.menu.addItem_(self.item_recent_header)

        self.recent_log_items = []
        for i in range(3):
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("  ...", "menuViewLogsAction:", "")
            item.setTarget_(self)
            self.recent_log_items.append(item)
            self.menu.addItem_(item)

        self.menu.addItem_(NSMenuItem.separatorItem())

        # Run in Menu Bar Only
        cfg = load_app_config()
        self.item_menu_bar_only = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Run in Menu Bar Only", "menuToggleMenuBarOnlyAction:", ""
        )
        self.item_menu_bar_only.setTarget_(self)
        self.item_menu_bar_only.setState_(NSControlStateValueOn if cfg.get("run_in_menu_bar_only", True) else NSControlStateValueOff)
        self.menu.addItem_(self.item_menu_bar_only)

        # Start at Login
        self.item_login = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Start at Login", "menuToggleLoginAction:", "")
        self.item_login.setTarget_(self)
        self.item_login.setState_(NSControlStateValueOn if is_start_at_login_enabled() else NSControlStateValueOff)
        self.menu.addItem_(self.item_login)

        self.menu.addItem_(NSMenuItem.separatorItem())

        # Quit (⌘Q)
        self.item_quit = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Quit CalendarSync", "menuQuitAction:", "q")
        self.item_quit.setKeyEquivalentModifierMask_(NSEventModifierFlagCommand)
        self.item_quit.setTarget_(self)
        self.menu.addItem_(self.item_quit)

        # Attach delegate and menu directly to status item
        self.menu.setDelegate_(self)
        self.status_item.setMenu_(self.menu)
        self._refresh_recent_log_menu_items()

    def menuWillOpen_(self, menu):
        """Called automatically right before the status menu opens."""
        self._refresh_recent_log_menu_items()

    def _refresh_recent_log_menu_items(self):
        """Update the 3 latest log entries in the menu bar dropdown."""
        entries = fetch_recent_log_entries(limit=3)
        for i in range(3):
            item = self.recent_log_items[i]
            if i < len(entries):
                raw = entries[i]
                formatted = format_menu_log_entry(raw)
                item.setTitle_(f"  {formatted}")
                item.setToolTip_(f"Log: {raw}\n(Click to view full Activity Logs)")
                item.setHidden_(False)
                item.setEnabled_(True)
            else:
                if i == 0 and not entries:
                    item.setTitle_("  (No recent log entries)")
                    item.setToolTip_("No logs recorded yet")
                    item.setHidden_(False)
                    item.setEnabled_(False)
                else:
                    item.setHidden_(True)

    def statusItemClicked_(self, sender):
        """Handle status bar button clicks if invoked directly."""
        if self.window_controller:
            self.window_controller.show_window(tab_index=1)

    def set_syncing_state(self, is_syncing: bool, stats: Optional[dict] = None, error: Optional[str] = None, dry_run: bool = False):
        """Dynamically update icon and menu items when sync state changes."""
        if is_syncing:
            if self._icon_syncing:
                self.status_item.button().setImage_(self._icon_syncing)
            else:
                self.status_item.button().setTitle_("🔄")
            mode_str = "Status: Dry Run..." if dry_run else "Status: Syncing..."
            self.item_status.setTitle_(f"CalendarSync • {mode_str}")
            self.item_sync_now.setEnabled_(False)
        else:
            if self._icon_idle:
                self.status_item.button().setImage_(self._icon_idle)
            else:
                self.status_item.button().setTitle_("📅")
            self.item_sync_now.setEnabled_(True)
            now_str = datetime.now().strftime("%H:%M")
            if error:
                self.item_status.setTitle_(f"CalendarSync • Error ({now_str})")
            elif stats:
                self.item_status.setTitle_(f"CalendarSync • Idle ({now_str})")
            else:
                self.item_status.setTitle_("CalendarSync • Ready")
            self._refresh_recent_log_menu_items()

    # --------------------------------------------------------------------------
    # Menu Action Selectors
    # --------------------------------------------------------------------------
    def menuSyncNowAction_(self, sender):
        if self.scheduler:
            self.scheduler.trigger_sync(dry_run=False, is_manual=True)

    def menuOpenSettingsAction_(self, sender):
        if self.window_controller:
            self.window_controller.show_window(tab_index=0)

    def menuViewLogsAction_(self, sender):
        if self.window_controller:
            self.window_controller.show_window(tab_index=1)

    def menuToggleMenuBarOnlyAction_(self, sender):
        current_state = self.item_menu_bar_only.state()
        new_state = NSControlStateValueOff if current_state == NSControlStateValueOn else NSControlStateValueOn
        self.item_menu_bar_only.setState_(new_state)
        menu_bar_only = bool(new_state == NSControlStateValueOn)

        if menu_bar_only:
            NSApp.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
        else:
            NSApp.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)

        cfg = load_app_config()
        cfg["run_in_menu_bar_only"] = menu_bar_only
        save_app_config(cfg)

        if self.window_controller and hasattr(self.window_controller, "chk_menu_bar_only"):
            self.window_controller.chk_menu_bar_only.setState_(new_state)

    def menuToggleLoginAction_(self, sender):
        current_state = self.item_login.state()
        new_state = NSControlStateValueOff if current_state == NSControlStateValueOn else NSControlStateValueOn
        success = set_start_at_login(new_state == NSControlStateValueOn)
        self.item_login.setState_(NSControlStateValueOn if success else NSControlStateValueOff)
        if self.window_controller and hasattr(self.window_controller, "chk_start_at_login"):
            self.window_controller.chk_start_at_login.setState_(self.item_login.state())

    def menuQuitAction_(self, sender):
        if self.scheduler:
            self.scheduler.stop()
        if self.window_controller and self.window_controller.window:
            self.window_controller.window.orderOut_(None)
        NSApp.terminate_(None)
        os._exit(0)


# ==============================================================================
# Application Delegate & Entry Point
# ==============================================================================
class AppDelegate(NSObject):
    """Coordinates lifecycle, status bar item, window controller, and scheduler."""

    def applicationDidFinishLaunching_(self, notification):
        # Set process name to CalendarSync
        try:
            from Foundation import NSProcessInfo
            NSProcessInfo.processInfo().setProcessName_("CalendarSync")
        except Exception:
            pass

        # Configure app activation policy based on configuration
        cfg = load_app_config()
        if cfg.get("run_in_menu_bar_only", True):
            NSApp.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
        else:
            NSApp.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)

        # Setup standard application main menu (Edit shortcuts, Window controls)
        self._build_main_menu()

        # Setup local keyboard shortcuts (⌘Q, ⌘W, ⌘,, ⌘L, ⌘S)
        self._setup_keyboard_shortcuts()

        # Register notification center delegate so notifications always display and respond to clicks
        try:
            from Foundation import NSUserNotificationCenter
            center = NSUserNotificationCenter.defaultUserNotificationCenter()
            center.setDelegate_(self)
        except Exception:
            pass

        # Initialize window controller
        self.window_ctrl = MainWindowController.alloc().init()

        # Initialize status item controller
        self.status_ctrl = StatusItemController.alloc().init()

        # Initialize sync scheduler with hooks
        self.scheduler = SyncScheduler(
            on_state_change=self._on_sync_state_change,
            on_log_update=self._on_log_update
        )

        self.window_ctrl.set_scheduler(self.scheduler)
        self.status_ctrl.set_dependencies(self.window_ctrl, self.scheduler)

        # Start scheduler loop
        self.scheduler.start()

        # If user opened the app explicitly without background daemon flag, show configuration window
        if "--minimized" not in sys.argv:
            self.window_ctrl.show_window(tab_index=0)

    def _setup_keyboard_shortcuts(self):
        """Intercept keyboard commands globally across the app window."""
        def key_handler(event):
            if event.type() == AppKit.NSEventTypeKeyDown:
                flags = event.modifierFlags() & AppKit.NSEventModifierFlagDeviceIndependentFlagsMask
                chars = event.charactersIgnoringModifiers()
                if flags == AppKit.NSEventModifierFlagCommand:
                    if chars == "q":
                        if hasattr(self, "scheduler") and self.scheduler:
                            self.scheduler.stop()
                        if hasattr(self, "window_ctrl") and self.window_ctrl and self.window_ctrl.window:
                            self.window_ctrl.window.orderOut_(None)
                        NSApp.terminate_(None)
                        os._exit(0)
                        return None
                    elif chars == "w":
                        if hasattr(self, "window_ctrl") and self.window_ctrl and self.window_ctrl.window and self.window_ctrl.window.isVisible():
                            self.window_ctrl.window.orderOut_(None)
                            return None
                    elif chars == ",":
                        if hasattr(self, "window_ctrl") and self.window_ctrl:
                            self.window_ctrl.show_window(tab_index=0)
                            return None
                    elif chars == "l":
                        if hasattr(self, "window_ctrl") and self.window_ctrl:
                            self.window_ctrl.show_window(tab_index=1)
                            return None
                    elif chars == "s":
                        if hasattr(self, "scheduler") and self.scheduler:
                            self.scheduler.trigger_sync(dry_run=False, is_manual=True)
                            return None
            return event

        AppKit.NSEvent.addLocalMonitorForEventsMatchingMask_handler_(AppKit.NSEventMaskKeyDown, key_handler)

    def _build_main_menu(self):
        """Construct the standard macOS application menu with Edit & Window menus."""
        main_menu = NSMenu.alloc().init()

        # 1. App Menu
        app_menu_item = NSMenuItem.alloc().init()
        main_menu.addItem_(app_menu_item)
        app_menu = NSMenu.alloc().initWithTitle_("CalendarSync")
        app_menu_item.setSubmenu_(app_menu)

        about_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("About CalendarSync", "orderFrontStandardAboutPanel:", "")
        app_menu.addItem_(about_item)
        app_menu.addItem_(NSMenuItem.separatorItem())

        pref_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Preferences...", "appOpenSettingsAction:", ",")
        pref_item.setTarget_(self)
        app_menu.addItem_(pref_item)
        app_menu.addItem_(NSMenuItem.separatorItem())

        hide_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Hide CalendarSync", "hide:", "h")
        app_menu.addItem_(hide_item)
        hide_others = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Hide Others", "hideOtherApplications:", "h")
        hide_others.setKeyEquivalentModifierMask_(AppKit.NSEventModifierFlagCommand | AppKit.NSEventModifierFlagOption)
        app_menu.addItem_(hide_others)
        show_all = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Show All", "unhideAllApplications:", "")
        app_menu.addItem_(show_all)
        app_menu.addItem_(NSMenuItem.separatorItem())

        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Quit CalendarSync", "terminate:", "q")
        app_menu.addItem_(quit_item)

        # 2. File / Action Menu
        file_menu_item = NSMenuItem.alloc().init()
        main_menu.addItem_(file_menu_item)
        file_menu = NSMenu.alloc().initWithTitle_("File")
        file_menu_item.setSubmenu_(file_menu)

        sync_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Sync Now", "appSyncNowAction:", "s")
        sync_item.setTarget_(self)
        file_menu.addItem_(sync_item)

        logs_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Activity Logs", "appViewLogsAction:", "l")
        logs_item.setTarget_(self)
        file_menu.addItem_(logs_item)
        file_menu.addItem_(NSMenuItem.separatorItem())

        close_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Close Window", "performClose:", "w")
        file_menu.addItem_(close_item)

        # 3. Edit Menu (⌘Z, ⇧⌘Z, ⌘X, ⌘C, ⌘V, ⌘A)
        edit_menu_item = NSMenuItem.alloc().init()
        main_menu.addItem_(edit_menu_item)
        edit_menu = NSMenu.alloc().initWithTitle_("Edit")
        edit_menu_item.setSubmenu_(edit_menu)

        edit_menu.addItem_(NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Undo", "undo:", "z"))
        redo_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Redo", "redo:", "Z")
        edit_menu.addItem_(redo_item)
        edit_menu.addItem_(NSMenuItem.separatorItem())
        edit_menu.addItem_(NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Cut", "cut:", "x"))
        edit_menu.addItem_(NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Copy", "copy:", "c"))
        edit_menu.addItem_(NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Paste", "paste:", "v"))
        edit_menu.addItem_(NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Select All", "selectAll:", "a"))

        # 4. Window Menu
        win_menu_item = NSMenuItem.alloc().init()
        main_menu.addItem_(win_menu_item)
        win_menu = NSMenu.alloc().initWithTitle_("Window")
        win_menu_item.setSubmenu_(win_menu)
        win_menu.addItem_(NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Minimize", "performMiniaturize:", "m"))
        win_menu.addItem_(NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Zoom", "performZoom:", ""))

        NSApp.setMainMenu_(main_menu)
        NSApp.setWindowsMenu_(win_menu)

    def userNotificationCenter_shouldPresentNotification_(self, center, notification):
        """Always present notifications even if app is focused."""
        return True

    def userNotificationCenter_didActivateNotification_(self, center, notification):
        """When user clicks a CalendarSync notification, show the Activity Logs tab."""
        if hasattr(self, "window_ctrl") and self.window_ctrl:
            self.window_ctrl.show_window(tab_index=1)

    def appSyncNowAction_(self, sender):
        if self.scheduler:
            self.scheduler.trigger_sync(dry_run=False, is_manual=True)

    def appOpenSettingsAction_(self, sender):
        if self.window_ctrl:
            self.window_ctrl.show_window(tab_index=0)

    def appViewLogsAction_(self, sender):
        if self.window_ctrl:
            self.window_ctrl.show_window(tab_index=1)

    def _on_sync_state_change(self, is_syncing: bool, stats: Optional[dict], error: Optional[str], dry_run: bool):
        self.status_ctrl.set_syncing_state(is_syncing, stats=stats, error=error, dry_run=dry_run)
        self.window_ctrl.update_sync_ui_state(is_syncing, stats=stats, error=error, dry_run=dry_run)

    def _on_log_update(self):
        self.window_ctrl.reload_logs()
        if hasattr(self, "status_ctrl") and self.status_ctrl:
            self.status_ctrl._refresh_recent_log_menu_items()

    def applicationWillTerminate_(self, notification):
        if hasattr(self, "scheduler") and self.scheduler:
            self.scheduler.stop()


def main():
    """Main launcher for CalendarSync native macOS application."""
    try:
        from Foundation import NSProcessInfo
        NSProcessInfo.processInfo().setProcessName_("CalendarSync")
    except Exception:
        pass
    app = NSApplication.sharedApplication()
    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
