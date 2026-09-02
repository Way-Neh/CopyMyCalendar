"""
mac_calendar.py - Interface for reading and writing macOS Calendar events via EventKit.
Uses exact unique calendarIdentifier as the primary lookup key.
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

import datetime
import hashlib
import json
import logging
import threading
from typing import List, Dict, Any, Optional

try:
    import EventKit
    from Foundation import NSDate
    EVENTKIT_AVAILABLE = True
except ImportError:
    EVENTKIT_AVAILABLE = False

logger = logging.getLogger("mac_calendar")


def nsdate_to_datetime(ns_date) -> Optional[datetime.datetime]:
    """Convert an NSDate object to Python datetime using local machine timezone."""
    if ns_date is None:
        return None
    timestamp = ns_date.timeIntervalSince1970()
    return datetime.datetime.fromtimestamp(timestamp).astimezone()


def datetime_to_nsdate(dt: datetime.datetime):
    """Convert Python datetime to NSDate."""
    if dt is None:
        return None
    if isinstance(dt, datetime.datetime):
        return NSDate.dateWithTimeIntervalSince1970_(dt.timestamp())
    return None


class MacCalendarClient:
    """Client for interacting with macOS Calendar via EventKit (Read & Write)."""

    def __init__(self):
        if not EVENTKIT_AVAILABLE:
            raise RuntimeError(
                "EventKit (pyobjc-framework-EventKit) is not installed.\n"
                "Please run: pip install pyobjc-framework-EventKit"
            )
        self.store = EventKit.EKEventStore.alloc().init()
        self._authorized = False

    def request_access(self) -> bool:
        """Request permission to access Calendar."""
        done_event = threading.Event()
        access_granted = [False]
        access_error = [None]

        def completion_handler(granted, error):
            access_granted[0] = bool(granted)
            access_error[0] = error
            done_event.set()

        if hasattr(self.store, "requestFullAccessToEventsWithCompletion_"):
            self.store.requestFullAccessToEventsWithCompletion_(completion_handler)
        else:
            self.store.requestAccessToEntityType_completion_(0, completion_handler)

        done_event.wait(timeout=30)
        self._authorized = access_granted[0]
        return self._authorized

    def _ensure_access(self):
        if not self._authorized:
            if not self.request_access():
                raise PermissionError(
                    "Calendar access was denied by macOS.\n"
                    "Please enable Calendar permissions in System Settings -> Privacy & Security -> Calendars."
                )

    def get_calendars(self, include_event_counts: bool = False) -> List[Dict[str, Any]]:
        """List all calendars available in macOS Calendar app with unique identifiers and event counts."""
        self._ensure_access()
        calendars = self.store.calendarsForEntityType_(0)  # EKEntityTypeEvent = 0
        result = []

        now = datetime.datetime.now().astimezone()
        s_date = datetime_to_nsdate(now - datetime.timedelta(days=365))
        e_date = datetime_to_nsdate(now + datetime.timedelta(days=365))

        for cal in calendars:
            event_count = None
            if include_event_counts:
                predicate = self.store.predicateForEventsWithStartDate_endDate_calendars_(
                    s_date, e_date, [cal]
                )
                evs = self.store.eventsMatchingPredicate_(predicate) or []
                event_count = len(evs)

            result.append({
                "title": str(cal.title()),
                "identifier": str(cal.calendarIdentifier()),
                "source": str(cal.source().title()) if cal.source() else "Local",
                "allows_modifications": bool(cal.allowsContentModifications()),
                "event_count_1yr": event_count
            })
        return result

    def get_calendar_by_id(self, calendar_id: str):
        """Find an EKCalendar object strictly by its unique calendarIdentifier."""
        self._ensure_access()
        if hasattr(self.store, "calendarWithIdentifier_"):
            cal = self.store.calendarWithIdentifier_(calendar_id)
            if cal:
                return cal

        calendars = self.store.calendarsForEntityType_(0)
        for cal in calendars:
            if str(cal.calendarIdentifier()) == str(calendar_id):
                return cal
        return None

    def event_exists(self, event_id: str) -> bool:
        """Check if an event exists in the macOS EventKit store."""
        try:
            self._ensure_access()
            ek_ev = self.store.eventWithIdentifier_(event_id)
            return ek_ev is not None
        except Exception:
            return False

    def get_events_by_calendar_id(
        self,
        calendar_id: str,
        start_date: datetime.datetime,
        end_date: datetime.datetime,
        chunk_days: int = 90
    ) -> List[Dict[str, Any]]:
        """Fetch all events for a given calendar unique ID within [start_date, end_date]."""
        target_cal = self.get_calendar_by_id(calendar_id)
        if not target_cal:
            available = [f"{c['title']} ({c['source']}) [ID: {c['identifier']}]" for c in self.get_calendars()]
            raise ValueError(
                f"Calendar ID '{calendar_id}' not found.\n"
                f"Available calendars:\n" + "\n".join(available)
            )

        events_by_id: Dict[str, Dict[str, Any]] = {}

        current_start = start_date
        while current_start < end_date:
            current_end = min(current_start + datetime.timedelta(days=chunk_days), end_date)

            ns_start = datetime_to_nsdate(current_start)
            ns_end = datetime_to_nsdate(current_end)

            predicate = self.store.predicateForEventsWithStartDate_endDate_calendars_(
                ns_start, ns_end, [target_cal]
            )
            ek_events = self.store.eventsMatchingPredicate_(predicate) or []

            for ek_ev in ek_events:
                event_dict = self._parse_ek_event(ek_ev)
                if event_dict and event_dict["id"] not in events_by_id:
                    events_by_id[event_dict["id"]] = event_dict

            current_start = current_end

        sorted_events = sorted(
            events_by_id.values(),
            key=lambda x: x["start"] if x["start"] else datetime.datetime.min.astimezone()
        )
        return sorted_events

    def search_all_calendars(
        self,
        query: str,
        start_date: datetime.datetime,
        end_date: datetime.datetime
    ) -> List[Dict[str, Any]]:
        """Search for events matching a query keyword across ALL calendars on the Mac."""
        self._ensure_access()
        calendars = self.store.calendarsForEntityType_(0)
        results = []

        query_lower = query.lower().strip()
        ns_start = datetime_to_nsdate(start_date)
        ns_end = datetime_to_nsdate(end_date)

        for cal in calendars:
            predicate = self.store.predicateForEventsWithStartDate_endDate_calendars_(
                ns_start, ns_end, [cal]
            )
            ek_events = self.store.eventsMatchingPredicate_(predicate) or []
            for ek_ev in ek_events:
                title = str(ek_ev.title()) if ek_ev.title() else ""
                if not query_lower or query_lower in title.lower():
                    parsed = self._parse_ek_event(ek_ev)
                    if parsed:
                        parsed["calendar_name"] = str(cal.title())
                        parsed["calendar_source"] = str(cal.source().title()) if cal.source() else "Local"
                        parsed["calendar_id"] = str(cal.calendarIdentifier())
                        results.append(parsed)

        return results

    def _parse_ek_event(self, ek_ev) -> Optional[Dict[str, Any]]:
        """Extract ONLY title and datetime information using machine local time."""
        raw_start = ek_ev.startDate()
        raw_end = ek_ev.endDate()
        if not raw_start or not raw_end:
            return None

        start_dt = nsdate_to_datetime(raw_start)
        end_dt = nsdate_to_datetime(raw_end)
        is_all_day = bool(ek_ev.isAllDay())
        title = str(ek_ev.title()) if ek_ev.title() else "(No Title)"
        base_id = str(ek_ev.eventIdentifier()) if ek_ev.eventIdentifier() else "unknown"

        start_ts = int(raw_start.timeIntervalSince1970())
        unique_instance_id = f"{base_id}_{start_ts}"

        content_payload = {
            "title": title,
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat(),
            "is_all_day": is_all_day,
        }

        content_hash = hashlib.sha256(
            json.dumps(content_payload, sort_keys=True).encode("utf-8")
        ).hexdigest()

        return {
            "id": unique_instance_id,
            "base_id": base_id,
            "title": title,
            "start": start_dt,
            "end": end_dt,
            "ns_start": raw_start,
            "ns_end": raw_end,
            "is_all_day": is_all_day,
            "content_hash": content_hash,
        }

    def create_event(
        self,
        target_calendar_id: str,
        event_data: Dict[str, Any]
    ) -> str:
        """Create a new event in the target calendar ID with only title and datetime."""
        target_cal = self.get_calendar_by_id(target_calendar_id)
        if not target_cal:
            raise ValueError(f"Target calendar ID '{target_calendar_id}' not found.")

        if not target_cal.allowsContentModifications():
            raise PermissionError(f"Target calendar '{target_cal.title()}' is read-only.")

        new_ev = EventKit.EKEvent.eventWithEventStore_(self.store)
        new_ev.setCalendar_(target_cal)
        self._apply_event_data(new_ev, event_data)

        if hasattr(self.store, "saveEvent_span_commit_error_"):
            success, error = self.store.saveEvent_span_commit_error_(new_ev, 0, True, None)
        else:
            success, error = self.store.saveEvent_span_error_(new_ev, 0, None)

        if not success:
            raise RuntimeError(f"Failed to create event in target calendar: {error}")

        return str(new_ev.eventIdentifier())

    def update_event(self, target_event_id: str, event_data: Dict[str, Any]) -> bool:
        """Update an existing event in the target calendar with only title and datetime."""
        self._ensure_access()
        ek_ev = self.store.eventWithIdentifier_(target_event_id)
        if not ek_ev:
            return False

        self._apply_event_data(ek_ev, event_data)
        if hasattr(self.store, "saveEvent_span_commit_error_"):
            success, error = self.store.saveEvent_span_commit_error_(ek_ev, 0, True, None)
        else:
            success, error = self.store.saveEvent_span_error_(ek_ev, 0, None)

        if not success:
            raise RuntimeError(f"Failed to update event {target_event_id}: {error}")
        return True

    def delete_event(self, target_event_id: str) -> bool:
        """Delete an event from the target calendar."""
        self._ensure_access()
        ek_ev = self.store.eventWithIdentifier_(target_event_id)
        if not ek_ev:
            return True

        if hasattr(self.store, "removeEvent_span_commit_error_"):
            success, error = self.store.removeEvent_span_commit_error_(ek_ev, 0, True, None)
        else:
            success, error = self.store.removeEvent_span_error_(ek_ev, 0, None)

        if not success:
            raise RuntimeError(f"Failed to delete event {target_event_id}: {error}")
        return True

    def clear_calendar(
        self,
        calendar_id: str,
        start_date: Optional[datetime.datetime] = None,
        end_date: Optional[datetime.datetime] = None
    ) -> int:
        """Delete ALL events in the specified calendar unique ID."""
        target_cal = self.get_calendar_by_id(calendar_id)
        if not target_cal:
            raise ValueError(f"Target calendar ID '{calendar_id}' not found.")
        if not target_cal.allowsContentModifications():
            raise PermissionError(f"Target calendar '{target_cal.title()}' is read-only.")

        now = datetime.datetime.now().astimezone()
        s_date = start_date or (now - datetime.timedelta(days=3650))
        e_date = end_date or (now + datetime.timedelta(days=3650))

        events = self.get_events_by_calendar_id(
            calendar_id=calendar_id,
            start_date=s_date,
            end_date=e_date,
            chunk_days=90
        )
        deleted_count = 0
        seen_base_ids = set()

        for ev in events:
            base_id = ev.get("base_id") or ev.get("id")
            if base_id in seen_base_ids:
                continue
            seen_base_ids.add(base_id)

            ek_ev = self.store.eventWithIdentifier_(base_id)
            if ek_ev:
                span = 1 if (hasattr(ek_ev, "hasRecurrenceRules") and ek_ev.hasRecurrenceRules()) else 0
                if hasattr(self.store, "removeEvent_span_commit_error_"):
                    success, error = self.store.removeEvent_span_commit_error_(ek_ev, span, True, None)
                else:
                    success, error = self.store.removeEvent_span_error_(ek_ev, span, None)
                if success:
                    deleted_count += 1

        self.commit()
        return deleted_count

    def commit(self):
        """Force flush and commit changes to the event store."""
        if hasattr(self.store, "commit_"):
            self.store.commit_(None)

    def _apply_event_data(self, ek_ev, data: Dict[str, Any]):
        """Populate an EKEvent object ONLY with title and datetime."""
        ek_ev.setTitle_(data.get("title") or "(No Title)")
        ek_ev.setAllDay_(bool(data.get("is_all_day", False)))

        if data.get("ns_start"):
            ek_ev.setStartDate_(data["ns_start"])
        elif data.get("start"):
            ek_ev.setStartDate_(datetime_to_nsdate(data["start"]))

        if data.get("ns_end"):
            ek_ev.setEndDate_(data["ns_end"])
        elif data.get("end"):
            ek_ev.setEndDate_(datetime_to_nsdate(data["end"]))

        ek_ev.setLocation_("")
        ek_ev.setNotes_("")
        ek_ev.setURL_(None)
        if hasattr(ek_ev, "setAlarms_"):
            ek_ev.setAlarms_([])
