"""
test_gui_app.py - Unit test suite for CalendarSync native macOS Cocoa GUI application.
"""

import os
import sys
import unittest
import tempfile
import yaml
from pathlib import Path

# Auto-inject project virtual environment site-packages if present
_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
_site_packages = [p for p in Path(_PROJECT_DIR).glob("venv/lib/python*/site-packages")]
for _sp in _site_packages:
    if str(_sp) not in sys.path:
        sys.path.insert(0, str(_sp))

import AppKit
import Foundation

from gui_app import (
    load_app_config,
    save_app_config,
    colorize_log_text,
    SyncScheduler,
    MainWindowController,
    StatusItemController,
    MainThreadDispatcher,
    CONFIG_FILE,
)


class TestGuiApp(unittest.TestCase):
    def setUp(self):
        self.app = AppKit.NSApplication.sharedApplication()
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_colorize_log_text(self):
        sample_log = (
            "================================================================================\n"
            "SYNC RUN (Machine Time): 2026-09-08 11:00:00\n"
            "SOURCE CALENDAR : 'Work' [ID: src_1]\n"
            "TARGET CALENDAR : 'Gmail' [ID: tgt_1]\n"
            "WINDOW          : 2026-09-01 to 2026-10-01 (7d past, 30d future)\n"
            "TOTAL DETECTED  : 5 source events found\n"
            "PLAN            : 1 to create | 1 to update | 1 to delete | 2 unchanged\n"
            "--------------------------------------------------------------------------------\n"
            "[CREATED]    | 2026-09-08 12:00 | Team Standup\n"
            "[UPDATED]    | 2026-09-08 14:00 | Client Review\n"
            "[DELETED]    | -                    | Target Event ID: tgt_old\n"
            "[UNCHANGED]  | 2026-09-08 16:00 | Coffee Chat\n"
            "[ERR CREATE] | 2026-09-08 17:00 | Bad Event\n"
            "[TO CREATE]  | 2026-09-09 10:00 | Preview Event\n"
            "================================================================================\n"
        )

        # Full text without filtering
        attr = colorize_log_text(sample_log)
        self.assertGreater(attr.length(), 0)

        # With filter query that matches
        attr_filtered = colorize_log_text(sample_log, filter_query="Standup")
        self.assertGreater(attr_filtered.length(), 0)
        self.assertLess(attr_filtered.length(), attr.length())
        self.assertIn("Team Standup", attr_filtered.string())
        self.assertNotIn("Client Review", attr_filtered.string())

        # With filter query that does not match
        attr_none = colorize_log_text(sample_log, filter_query="NonexistentKeyword12345")
        self.assertEqual(attr_none.length(), 0)

    def test_config_load_and_save(self):
        test_cfg_path = os.path.join(self.temp_dir.name, "test_config.yaml")
        test_data = {
            "source_calendar_name": "Test Source",
            "source_calendar_id": "SRC-UUID-1234",
            "target_calendar_name": "Test Target",
            "target_calendar_id": "TGT-UUID-5678",
            "rolling_days_past": 14,
            "rolling_days_future": 60,
            "sync_interval_minutes": 30,
            "state_db_file": "test_state.db"
        }

        with open(test_cfg_path, "w") as f:
            yaml.dump(test_data, f)

        # Test reading file
        with open(test_cfg_path, "r") as f:
            loaded = yaml.safe_load(f)

        self.assertEqual(loaded["source_calendar_id"], "SRC-UUID-1234")
        self.assertEqual(loaded["rolling_days_past"], 14)
        self.assertEqual(loaded["rolling_days_future"], 60)
        self.assertEqual(loaded["sync_interval_minutes"], 30)

    def test_sync_scheduler_interval_logic(self):
        sched = SyncScheduler()
        self.assertFalse(sched.is_syncing)
        self.assertGreaterEqual(sched.interval_seconds, 60)

        sched.update_interval_minutes(45)
        self.assertEqual(sched.interval_seconds, 45 * 60)

        # Minimum clamp
        sched.update_interval_minutes(0)
        self.assertEqual(sched.interval_seconds, 60)

    def test_main_window_controller_initialization(self):
        win_ctrl = MainWindowController.alloc().init()
        self.assertIsNotNone(win_ctrl)
        self.assertIsNotNone(win_ctrl.window)
        self.assertIsNotNone(win_ctrl.backdrop)
        self.assertIsNotNone(win_ctrl.seg_ctrl)
        self.assertIsNotNone(win_ctrl.config_view)
        self.assertIsNotNone(win_ctrl.logs_view)

        # Verify segments
        self.assertEqual(win_ctrl.seg_ctrl.segmentCount(), 2)
        self.assertEqual(win_ctrl.seg_ctrl.labelForSegment_(0), "Configuration")
        self.assertEqual(win_ctrl.seg_ctrl.labelForSegment_(1), "Activity Logs")

        # Verify controls in config view
        self.assertIsNotNone(win_ctrl.pop_source)
        self.assertIsNotNone(win_ctrl.pop_target)
        self.assertIsNotNone(win_ctrl.tf_past)
        self.assertIsNotNone(win_ctrl.tf_future)
        self.assertIsNotNone(win_ctrl.tf_interval)
        self.assertIsNotNone(win_ctrl.btn_save)
        self.assertIsNotNone(win_ctrl.btn_sync_now)
        self.assertIsNotNone(win_ctrl.btn_dry_run)
        self.assertIsNotNone(win_ctrl.btn_reset_state)
        self.assertIsNotNone(win_ctrl.btn_clear_target)

        # Verify controls in logs view
        self.assertIsNotNone(win_ctrl.search_field)
        self.assertIsNotNone(win_ctrl.chk_autoscroll)
        self.assertIsNotNone(win_ctrl.btn_copy_logs)
        self.assertIsNotNone(win_ctrl.btn_clear_logs)
        self.assertIsNotNone(win_ctrl.btn_finder)
        self.assertIsNotNone(win_ctrl.log_text_view)

        # Verify Quit buttons
        self.assertIsNotNone(win_ctrl.btn_header_quit)
        self.assertEqual(win_ctrl.btn_header_quit.action(), "quitAppAction:")
        self.assertIsNotNone(win_ctrl.btn_quit_footer)
        self.assertEqual(win_ctrl.btn_quit_footer.action(), "quitAppAction:")

    def test_status_item_controller_initialization(self):
        status_ctrl = StatusItemController.alloc().init()
        self.assertIsNotNone(status_ctrl)
        self.assertIsNotNone(status_ctrl.status_item)
        self.assertIsNotNone(status_ctrl.menu)

        # Check menu items
        titles = [status_ctrl.menu.itemAtIndex_(i).title() for i in range(status_ctrl.menu.numberOfItems())]
        self.assertTrue(any("Status:" in t for t in titles))
        self.assertTrue(any("Sync Now" in t for t in titles))
        self.assertTrue(any("Configuration" in t or "Settings" in t for t in titles))
        self.assertTrue(any("View Activity Logs" in t for t in titles))
        self.assertTrue(any("Run in Menu Bar Only" in t for t in titles))
        self.assertTrue(any("Start at Login" in t for t in titles))
        self.assertTrue(any("Quit" in t for t in titles))

        # Check button action and click wiring
        btn = status_ctrl.status_item.button()
        self.assertIsNotNone(btn)
        self.assertEqual(btn.action(), "statusItemClicked:")

        # Check keyboard shortcuts
        item_sync = next(item for item in status_ctrl.menu.itemArray() if item.title() == "Sync Now")
        self.assertEqual(item_sync.keyEquivalent(), "s")

        item_quit = next(item for item in status_ctrl.menu.itemArray() if "Quit" in item.title())
        self.assertEqual(item_quit.keyEquivalent(), "q")

        # Check recent log entries in menu bar
        self.assertEqual(len(status_ctrl.recent_log_items), 3)
        self.assertTrue(any("Recent Activity Logs:" in t for t in titles))

        # Test state transition
        status_ctrl.set_syncing_state(True, dry_run=False)
        self.assertIn("Syncing", status_ctrl.item_status.title())
        self.assertFalse(status_ctrl.item_sync_now.isEnabled())

        status_ctrl.set_syncing_state(False, stats={"created": 1, "updated": 0, "deleted": 0})
        self.assertIn("Idle", status_ctrl.item_status.title())
        self.assertTrue(status_ctrl.item_sync_now.isEnabled())

    def test_menu_bar_recent_log_entries(self):
        from gui_app import fetch_recent_log_entries, format_menu_log_entry
        entries = fetch_recent_log_entries(limit=3)
        self.assertIsInstance(entries, list)
        self.assertLessEqual(len(entries), 3)

        formatted_created = format_menu_log_entry("[CREATED] 2026-10-08 09:00 | Standup")
        self.assertTrue(formatted_created.startswith("🟢"))

        formatted_unchanged = format_menu_log_entry("[UNCHANGED] 2026-10-08 09:00 | Standup")
        self.assertTrue(formatted_unchanged.startswith("⚪️"))

        status_ctrl = StatusItemController.alloc().init()
        status_ctrl.menuWillOpen_(status_ctrl.menu)
        self.assertEqual(len(status_ctrl.recent_log_items), 3)
        for item in status_ctrl.recent_log_items:
            self.assertEqual(item.action(), "menuViewLogsAction:")

    def test_status_item_click_action(self):
        status_ctrl = StatusItemController.alloc().init()
        win_ctrl = MainWindowController.alloc().init()
        status_ctrl.set_dependencies(win_ctrl, None)

        # Trigger left click simulation
        status_ctrl.statusItemClicked_(None)
        # Should switch to Activity Logs tab (index 1)
        self.assertEqual(win_ctrl.seg_ctrl.selectedSegment(), 1)
        self.assertTrue(win_ctrl.config_view.isHidden())
        self.assertFalse(win_ctrl.logs_view.isHidden())

    def test_menu_bar_only_toggle(self):
        status_ctrl = StatusItemController.alloc().init()
        win_ctrl = MainWindowController.alloc().init()
        status_ctrl.set_dependencies(win_ctrl, None)

        init_state = status_ctrl.item_menu_bar_only.state()
        status_ctrl.menuToggleMenuBarOnlyAction_(None)
        self.assertNotEqual(status_ctrl.item_menu_bar_only.state(), init_state)
        # Toggle back
        status_ctrl.menuToggleMenuBarOnlyAction_(None)
        self.assertEqual(status_ctrl.item_menu_bar_only.state(), init_state)

    def test_app_delegate_main_menu(self):
        from gui_app import AppDelegate
        delegate = AppDelegate.alloc().init()
        delegate._build_main_menu()

        main_menu = AppKit.NSApp.mainMenu()
        self.assertIsNotNone(main_menu)
        menu_titles = [
            main_menu.itemAtIndex_(i).submenu().title()
            for i in range(main_menu.numberOfItems())
            if main_menu.itemAtIndex_(i).submenu()
        ]
        self.assertIn("File", menu_titles)
        self.assertIn("Edit", menu_titles)
        self.assertIn("Window", menu_titles)

        # Inspect Edit menu items
        edit_item = next(
            item for item in main_menu.itemArray()
            if item.submenu() and item.submenu().title() == "Edit"
        )
        self.assertIsNotNone(edit_item)
        edit_sub = edit_item.submenu()
        edit_actions = [edit_sub.itemAtIndex_(i).action() for i in range(edit_sub.numberOfItems())]
        self.assertIn("copy:", edit_actions)
        self.assertIn("paste:", edit_actions)
        self.assertIn("selectAll:", edit_actions)
        self.assertIn("undo:", edit_actions)

    def test_main_thread_dispatcher(self):
        executed = [False]

        def callback(val):
            executed[0] = val

        MainThreadDispatcher.run_on_main(callback, True)
        Foundation.NSRunLoop.currentRunLoop().runUntilDate_(
            Foundation.NSDate.dateWithTimeIntervalSinceNow_(0.05)
        )
        self.assertTrue(executed[0])


if __name__ == "__main__":
    unittest.main()
