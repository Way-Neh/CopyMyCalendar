"""
test_outlook_calendar.py - Unit tests for Outlook calendar client and recurrence expansion.
"""

import os
import unittest
import datetime
from dateutil import tz

from outlook_calendar import OutlookCalendarClient, unescape_ics_text


class TestOutlookCalendar(unittest.TestCase):
    def setUp(self):
        self.client = OutlookCalendarClient()
        self.local_tz = datetime.datetime.now().astimezone().tzinfo

    def test_unescape_ics_text(self):
        raw = r"Team Sync\, Weekly\; Review\\Notes\nNew Line"
        unescaped = self.client._unescape_ics_text(raw)
        self.assertEqual(unescaped, "Team Sync, Weekly; Review\\Notes New Line")

    def test_parse_ics_datetime(self):
        # 1. UTC format
        dt_utc, is_all_day, orig_tz = self.client._parse_ics_datetime("20260713T130000Z", self.local_tz)
        self.assertFalse(is_all_day)
        self.assertIsNotNone(dt_utc)
        self.assertEqual(dt_utc.tzinfo, self.local_tz)

        # 2. Local/Floating format
        dt_local, is_all_day, orig_tz = self.client._parse_ics_datetime("20260713T210000", self.local_tz)
        self.assertFalse(is_all_day)
        self.assertEqual(dt_local.year, 2026)
        self.assertEqual(dt_local.hour, 21)

        # 3. All-day date format
        dt_all_day, is_all_day, orig_tz = self.client._parse_ics_datetime("20260713", self.local_tz)
        self.assertTrue(is_all_day)
        self.assertEqual(dt_all_day.day, 13)

        # 4. TZID format
        dt_tzid, is_all_day, orig_tz = self.client._parse_ics_datetime('DTSTART;TZID="W. Europe Standard Time":20260604T100000', self.local_tz)
        self.assertFalse(is_all_day)
        self.assertEqual(dt_tzid.hour, 16) # 10:00 CEST (UTC+2) -> 16:00 SGT (UTC+8)

    def test_expand_ics_recurring_series(self):
        sample_ics = r"""
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Microsoft Corporation//Outlook for Mac MIMEDIR//EN
BEGIN:VEVENT
UID:040000008200E00074C5B7101A82E008000000004A32EFA07A10DD0100000000000000001000000041D8A64FBB28BE4DA4B785AB7317A1EF
DTSTART:20260713T210000
DTEND:20260713T230000
SUMMARY:Daily Standup\, Team
RRULE:FREQ=DAILY;INTERVAL=1;UNTIL=20260716T235959
END:VEVENT
BEGIN:VEVENT
RECURRENCE-ID:20260715T210000
DTSTART:20260715T220000
DTEND:20260715T233000
SUMMARY:Special Standup (Moved)
END:VEVENT
END:VCALENDAR
"""
        window_start = datetime.datetime(2026, 7, 12, 0, 0, tzinfo=self.local_tz)
        window_end = datetime.datetime(2026, 7, 18, 0, 0, tzinfo=self.local_tz)
        results = {}

        self.client._expand_ics_recurring_series(
            eid="999",
            ics_blob=sample_ics,
            window_start=window_start,
            window_end=window_end,
            local_tz=self.local_tz,
            results_dict=results
        )

        self.assertEqual(len(results), 4) # 13th, 14th, 15th (exception), 16th

        # Check titles
        titles = [ev["title"] for ev in results.values()]
        self.assertIn("Daily Standup, Team", titles)
        self.assertIn("[Moved] Special Standup (Moved)", titles)

        # Check exception event time
        exc_ev = [ev for ev in results.values() if ev["title"] == "[Moved] Special Standup (Moved)"][0]
        self.assertEqual(exc_ev["start"].hour, 22)
        self.assertEqual(exc_ev["end"].minute, 30)
        # Verify stable slot tracking ID
        self.assertTrue(exc_ev["id"].startswith("outlook_999_occ_"))


if __name__ == "__main__":
    unittest.main()
