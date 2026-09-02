"""
test_sync_engine.py - Unit test suite for sync state store, diff engine, and logging.
"""

import os
import unittest
import tempfile
import datetime
import hashlib
import json

from sync_engine import SyncStateStore, SyncEngine


class MockMacCalendarClient:
    def __init__(self, source_events=None):
        self.source_events = source_events or []
        self.target_events = {}
        self.created = []
        self.updated = []
        self.deleted = []
        self.id_counter = 100

    def get_events_by_calendar_id(self, calendar_id, start_date, end_date, chunk_days=90):
        if calendar_id == "src_cal_id":
            return self.source_events
        return list(self.target_events.values())

    def event_exists(self, event_id):
        return event_id in self.target_events

    def create_event(self, target_calendar_id, event_data):
        self.id_counter += 1
        tgt_id = f"tgt_{self.id_counter}"
        self.target_events[tgt_id] = event_data
        self.created.append((target_calendar_id, tgt_id, event_data))
        return tgt_id

    def update_event(self, target_event_id, event_data):
        self.updated.append((target_event_id, event_data))
        self.target_events[target_event_id] = event_data
        return True

    def delete_event(self, target_event_id):
        self.deleted.append(target_event_id)
        if target_event_id in self.target_events:
            del self.target_events[target_event_id]
        return True

    def clear_calendar(self, calendar_id, start_date=None, end_date=None):
        count = len(self.target_events)
        self.target_events.clear()
        return count

    def commit(self):
        pass


def make_event(event_id, title, start_dt, end_dt, is_all_day=False):
    payload = {
        "title": title,
        "start": start_dt.isoformat(),
        "end": end_dt.isoformat(),
        "is_all_day": is_all_day,
    }
    h = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return {
        "id": event_id,
        "title": title,
        "start": start_dt,
        "end": end_dt,
        "is_all_day": is_all_day,
        "content_hash": h
    }


class TestSyncEngine(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_sync.db")
        self.log_path = os.path.join(self.temp_dir.name, "test_sync_events.log")
        self.state_store = SyncStateStore(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_state_store_crud(self):
        now_local = datetime.datetime.now().astimezone()
        self.state_store.save_mapping("src1", "tgt1", "hash1", now_local.isoformat(), (now_local + datetime.timedelta(hours=1)).isoformat())
        mappings = self.state_store.get_all_mappings()
        self.assertIn("src1", mappings)
        self.assertEqual(mappings["src1"]["target_event_id"], "tgt1")
        self.assertEqual(mappings["src1"]["content_hash"], "hash1")

        self.state_store.remove_mapping("src1")
        self.assertNotIn("src1", self.state_store.get_all_mappings())

    def test_sync_cycle_and_clear_target(self):
        now = datetime.datetime.now().astimezone()
        ev1 = make_event("src1_100", "Meeting 1", now + datetime.timedelta(days=1), now + datetime.timedelta(days=1, hours=1))
        ev2 = make_event("src2_200", "Meeting 2", now + datetime.timedelta(days=2), now + datetime.timedelta(days=2, hours=1))

        mac_client = MockMacCalendarClient(source_events=[ev1, ev2])

        engine = SyncEngine(
            mac_client=mac_client,
            state_store=self.state_store,
            source_calendar_id="src_cal_id",
            target_calendar_id="tgt_cal_id",
            source_calendar_name="Source",
            target_calendar_name="Target",
            days_past=365,
            days_future=730
        )

        stats1 = engine.sync(log_file=self.log_path)
        self.assertEqual(stats1["created"], 2)
        self.assertEqual(len(mac_client.target_events), 2)
        self.assertEqual(len(self.state_store.get_all_mappings()), 2)

        deleted = engine.clear_target_calendar()
        self.assertEqual(deleted, 2)
        self.assertEqual(len(mac_client.target_events), 0)
        self.assertEqual(len(self.state_store.get_all_mappings()), 0)


if __name__ == "__main__":
    unittest.main()
