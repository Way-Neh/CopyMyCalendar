"""
sync_engine.py - Core sync logic and SQLite state store using unique calendar identifiers.
"""

import os
import sys
import glob

# Auto-inject project virtual environment site-packages if present
_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
_site_packages = glob.glob(os.path.join(_PROJECT_DIR, "venv", "lib", "python*", "site-packages"))
for _sp in _site_packages:
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

import sqlite3
import datetime
import logging
from typing import Dict, Any, List, Optional, Tuple

SYNC_LOG_FILE = "sync_events.log"


class SyncStateStore:
    """SQLite-backed store to track mappings between Source and Target calendar events."""

    def __init__(self, db_path: str = "sync_state.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS event_mappings (
                    source_event_id TEXT PRIMARY KEY,
                    target_event_id TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    start_time TEXT,
                    end_time TEXT,
                    last_synced_at TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sync_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            conn.commit()

    def get_all_mappings(self) -> Dict[str, Dict[str, Any]]:
        """Retrieve all currently mapped events."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT source_event_id, target_event_id, content_hash, start_time, end_time FROM event_mappings"
            )
            rows = cursor.fetchall()
            return {
                row["source_event_id"]: {
                    "target_event_id": row["target_event_id"],
                    "content_hash": row["content_hash"],
                    "start_time": row["start_time"],
                    "end_time": row["end_time"],
                }
                for row in rows
            }

    def save_mapping(self, source_id: str, target_id: str, content_hash: str, start_time: str, end_time: str):
        """Insert or replace an event mapping using machine local time."""
        now_str = datetime.datetime.now().astimezone().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO event_mappings 
                (source_event_id, target_event_id, content_hash, start_time, end_time, last_synced_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (source_id, target_id, content_hash, start_time, end_time, now_str))
            conn.commit()

    def remove_mapping(self, source_id: str):
        """Remove an event mapping."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM event_mappings WHERE source_event_id = ?", (source_id,))
            conn.commit()

    def clear_all_mappings(self):
        """Clear all event mappings."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM event_mappings")
            cursor.execute("DELETE FROM sync_meta WHERE key = 'last_sync_time'")
            conn.commit()

    def get_meta(self, key: str) -> Optional[str]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM sync_meta WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row["value"] if row else None

    def set_meta(self, key: str, value: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO sync_meta (key, value) VALUES (?, ?)", (key, value))
            conn.commit()


class SyncEngine:
    """Orchestrates syncing between source and target calendars using unique calendar IDs."""

    def __init__(
        self,
        mac_client=None,
        state_store: SyncStateStore = None,
        source_calendar_id: str = "",
        target_calendar_id: str = "",
        source_calendar_name: str = "Source",
        target_calendar_name: str = "Target",
        days_past: int = 365,
        days_future: int = 730,
        source_client=None,
        target_client=None,
    ):
        self.state_store = state_store
        self.source_calendar_id = str(source_calendar_id)
        self.target_calendar_id = str(target_calendar_id)
        self.source_calendar_name = source_calendar_name
        self.target_calendar_name = target_calendar_name
        self.days_past = days_past
        self.days_future = days_future

        # Automatically resolve source client
        if source_client is not None:
            self.source_client = source_client
        elif self.source_calendar_id.startswith("outlook:") or (self.source_calendar_id.isdigit() and len(self.source_calendar_id) < 8):
            try:
                from outlook_calendar import OutlookCalendarClient
                self.source_client = OutlookCalendarClient()
            except Exception as e:
                logger.warning(f"Could not load OutlookCalendarClient, falling back: {e}")
                self.source_client = mac_client
        else:
            self.source_client = mac_client

        # Automatically resolve target client
        if target_client is not None:
            self.target_client = target_client
        elif self.target_calendar_id.startswith("outlook:") or (self.target_calendar_id.isdigit() and len(self.target_calendar_id) < 8):
            try:
                from outlook_calendar import OutlookCalendarClient
                self.target_client = OutlookCalendarClient()
            except Exception as e:
                self.target_client = mac_client
        else:
            self.target_client = mac_client

        # Backward compatibility alias
        self.mac_client = self.target_client or self.source_client

    def clear_target_calendar(self, start_date: Optional[datetime.datetime] = None, end_date: Optional[datetime.datetime] = None) -> int:
        """Delete ALL events in the target calendar ID and reset state."""
        deleted_count = self.target_client.clear_calendar(
            calendar_id=self.target_calendar_id,
            start_date=start_date,
            end_date=end_date
        )
        self.state_store.clear_all_mappings()

        now = datetime.datetime.now().astimezone()
        log_entry = (
            f"================================================================================\n"
            f"CLEAR TARGET CALENDAR: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
            f"TARGET CALENDAR : '{self.target_calendar_name}' [ID: {self.target_calendar_id}]\n"
            f"DELETED EVENTS  : {deleted_count} events deleted\n"
            f"MAPPINGS STORE  : Cleared sync_state.db\n"
            f"================================================================================\n\n"
        )
        with open(SYNC_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_entry)

        return deleted_count

    def compute_diff(
        self,
        start_date: datetime.datetime,
        end_date: datetime.datetime
    ) -> Tuple[List[Dict[str, Any]], List[Tuple[Dict[str, Any], str]], List[Tuple[str, str]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Compute differences between source and target calendars using unique calendar IDs."""
        source_events = self.source_client.get_events_by_calendar_id(
            calendar_id=self.source_calendar_id,
            start_date=start_date,
            end_date=end_date
        )
        existing_mappings = self.state_store.get_all_mappings()

        source_events_map = {ev["id"]: ev for ev in source_events}

        to_create = []
        to_update = []
        unchanged = []
        to_delete = []

        for src_id, ev in source_events_map.items():
            if src_id not in existing_mappings:
                to_create.append(ev)
            else:
                mapping = existing_mappings[src_id]
                target_id = mapping["target_event_id"]
                target_still_exists = True
                if hasattr(self.target_client, "event_exists"):
                    target_still_exists = self.target_client.event_exists(target_id)

                if not target_still_exists:
                    to_create.append(ev)
                elif mapping["content_hash"] != ev["content_hash"]:
                    to_update.append((ev, target_id))
                else:
                    unchanged.append(ev)

        start_iso = start_date.isoformat()
        end_iso = end_date.isoformat()

        for src_id, mapping in existing_mappings.items():
            if src_id not in source_events_map:
                event_start = mapping.get("start_time")
                if event_start and (start_iso <= event_start <= end_iso):
                    to_delete.append((src_id, mapping["target_event_id"]))

        return to_create, to_update, to_delete, unchanged, source_events

    def sync(self, dry_run: bool = False, log_file: str = SYNC_LOG_FILE) -> Dict[str, Any]:
        """Execute a synchronization run using unique calendar IDs."""
        now = datetime.datetime.now().astimezone()
        start_date = now - datetime.timedelta(days=self.days_past)
        end_date = now + datetime.timedelta(days=self.days_future)

        to_create, to_update, to_delete, unchanged, all_source_events = self.compute_diff(start_date, end_date)

        log_entries = []
        log_entries.append(f"================================================================================")
        log_entries.append(f"SYNC RUN (Machine Time): {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        log_entries.append(f"SOURCE CALENDAR : '{self.source_calendar_name}' [ID: {self.source_calendar_id}]")
        log_entries.append(f"TARGET CALENDAR : '{self.target_calendar_name}' [ID: {self.target_calendar_id}]")
        log_entries.append(f"WINDOW          : {start_date.strftime('%Y-%m-%d %H:%M')} to {end_date.strftime('%Y-%m-%d %H:%M')} ({self.days_past}d past, {self.days_future}d future)")
        log_entries.append(f"TOTAL DETECTED  : {len(all_source_events)} source events found")
        log_entries.append(f"PLAN            : {len(to_create)} to create | {len(to_update)} to update | {len(to_delete)} to delete | {len(unchanged)} unchanged")
        log_entries.append(f"MODE            : {'DRY RUN (Preview)' if dry_run else 'REAL SYNC'}")
        log_entries.append(f"--------------------------------------------------------------------------------")
        log_entries.append(f"{'STATUS':<12} | {'LOCAL MACHINE TIME':<22} | {'EVENT TITLE'}")
        log_entries.append(f"--------------------------------------------------------------------------------")

        if not dry_run:
            for ev in to_create:
                try:
                    target_id = self.target_client.create_event(
                        target_calendar_id=self.target_calendar_id,
                        event_data=ev
                    )
                    start_str = ev["start"].isoformat() if ev["start"] else ""
                    end_str = ev["end"].isoformat() if ev["end"] else ""
                    self.state_store.save_mapping(
                        source_id=ev["id"],
                        target_id=target_id,
                        content_hash=ev["content_hash"],
                        start_time=start_str,
                        end_time=end_str
                    )
                    log_entries.append(f"[CREATED]    | {self._format_dt(ev['start']):<22} | {ev['title']}")
                except Exception as e:
                    log_entries.append(f"[ERR CREATE] | {self._format_dt(ev['start']):<22} | {ev['title']} (Error: {e})")

            for ev, target_id in to_update:
                try:
                    updated = self.target_client.update_event(target_id, ev)
                    if not updated:
                        target_id = self.target_client.create_event(
                            target_calendar_id=self.target_calendar_id,
                            event_data=ev
                        )
                    start_str = ev["start"].isoformat() if ev["start"] else ""
                    end_str = ev["end"].isoformat() if ev["end"] else ""
                    self.state_store.save_mapping(
                        source_id=ev["id"],
                        target_id=target_id,
                        content_hash=ev["content_hash"],
                        start_time=start_str,
                        end_time=end_str
                    )
                    log_entries.append(f"[UPDATED]    | {self._format_dt(ev['start']):<22} | {ev['title']}")
                except Exception as e:
                    log_entries.append(f"[ERR UPDATE] | {self._format_dt(ev['start']):<22} | {ev['title']} (Error: {e})")

            for src_id, target_id in to_delete:
                try:
                    self.target_client.delete_event(target_id)
                    self.state_store.remove_mapping(src_id)
                    log_entries.append(f"[DELETED]    | {'-':<22} | Target Event ID: {target_id}")
                except Exception as e:
                    log_entries.append(f"[ERR DELETE] | {'-':<22} | Target Event ID: {target_id} (Error: {e})")

            for ev in unchanged:
                log_entries.append(f"[UNCHANGED]  | {self._format_dt(ev['start']):<22} | {ev['title']}")

            if hasattr(self.target_client, "commit"):
                self.target_client.commit()

            self.state_store.set_meta("last_sync_time", now.isoformat())
            self.state_store.set_meta("source_calendar_id", self.source_calendar_id)
            self.state_store.set_meta("target_calendar_id", self.target_calendar_id)

        else:
            for ev in to_create:
                log_entries.append(f"[TO CREATE]  | {self._format_dt(ev['start']):<22} | {ev['title']}")
            for ev, _ in to_update:
                log_entries.append(f"[TO UPDATE]  | {self._format_dt(ev['start']):<22} | {ev['title']}")
            for src_id, target_id in to_delete:
                log_entries.append(f"[TO DELETE]  | {'-':<22} | Target Event ID: {target_id}")
            for ev in unchanged:
                log_entries.append(f"[UNCHANGED]  | {self._format_dt(ev['start']):<22} | {ev['title']}")

        log_entries.append(f"================================================================================\n")

        with open(log_file, "a", encoding="utf-8") as f:
            f.write("\n".join(log_entries) + "\n")

        return {
            "created": len(to_create),
            "updated": len(to_update),
            "deleted": len(to_delete),
            "unchanged": len(unchanged),
            "total_source_events": len(all_source_events),
            "dry_run": dry_run,
            "timestamp": now.isoformat(),
            "log_file": log_file
        }

    def _format_dt(self, dt: Optional[datetime.datetime]) -> str:
        if not dt:
            return "N/A"
        return dt.strftime("%Y-%m-%d %H:%M")
