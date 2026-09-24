"""
outlook_calendar.py - Interface for reading Microsoft Outlook calendar events via AppleScript / NSAppleScript.
Supports both single and recurring calendar events, expanding recurrence rules into machine local time.
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

import re
import json
import hashlib
import logging
import datetime
import subprocess
from typing import List, Dict, Any, Optional, Tuple
from dateutil import rrule, tz

try:
    from Foundation import NSAppleScript, NSDictionary
    FOUNDATION_AVAILABLE = True
except ImportError:
    FOUNDATION_AVAILABLE = False

logger = logging.getLogger("outlook_calendar")


def run_applescript(script_str: str, timeout: int = 120) -> Tuple[bool, str]:
    """Execute AppleScript string using subprocess osascript with timeout."""
    try:
        res = subprocess.run(
            ["osascript", "-e", script_str],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        if res.returncode != 0:
            err = res.stderr.strip()
            if "-1743" in err or "Not authorized to send Apple events" in err:
                return False, (
                    "Automation permission denied by macOS (-1743). "
                    "Please open System Settings -> Privacy & Security -> Automation and ensure "
                    "Microsoft Outlook is toggled ON under CalendarSync (or Terminal/Python)."
                )
            elif "isn’t running" in err or "is not running" in err:
                return False, "Microsoft Outlook is not running. Please launch Outlook."
            elif "-1712" in err or "timed out" in err.lower():
                return False, f"Outlook query timed out after {timeout}s. Please ensure Outlook is responsive."
            return False, err
        return True, res.stdout.strip()
    except subprocess.TimeoutExpired:
        return False, f"AppleScript execution timed out after {timeout} seconds"
    except Exception as e:
        return False, str(e)


# Comprehensive Windows / Exchange Time Zone to IANA / zoneinfo map
WINDOWS_TO_IANA_TZ = {
    "Dateline Standard Time": "Etc/GMT+12",
    "UTC-11": "Etc/GMT+11",
    "Aleutian Standard Time": "America/Adak",
    "Hawaiian Standard Time": "Pacific/Honolulu",
    "Marquesas Standard Time": "Pacific/Marquesas",
    "Alaskan Standard Time": "America/Anchorage",
    "UTC-09": "Etc/GMT+9",
    "Pacific Standard Time (Mexico)": "America/Tijuana",
    "UTC-08": "Etc/GMT+8",
    "Pacific Standard Time": "America/Los_Angeles",
    "US Mountain Standard Time": "America/Phoenix",
    "Mountain Standard Time (Mexico)": "America/Chihuahua",
    "Mountain Standard Time": "America/Denver",
    "Yukon Standard Time": "America/Whitehorse",
    "Central America Standard Time": "America/Guatemala",
    "Central Standard Time": "America/Chicago",
    "Easter Island Standard Time": "Pacific/Easter",
    "Central Standard Time (Mexico)": "America/Mexico_City",
    "Canada Central Standard Time": "America/Regina",
    "SA Pacific Standard Time": "America/Bogota",
    "Eastern Standard Time (Mexico)": "America/Cancun",
    "Eastern Standard Time": "America/New_York",
    "Haiti Standard Time": "America/Port-au-Prince",
    "Cuba Standard Time": "America/Havana",
    "US Eastern Standard Time": "America/Indianapolis",
    "Turks And Caicos Standard Time": "America/Grand_Turk",
    "Paraguay Standard Time": "America/Asuncion",
    "Atlantic Standard Time": "America/Halifax",
    "Venezuela Standard Time": "America/Caracas",
    "Central Brazilian Standard Time": "America/Cuiaba",
    "SA Western Standard Time": "America/La_Paz",
    "Pacific SA Standard Time": "America/Santiago",
    "Newfoundland Standard Time": "America/St_Johns",
    "Tocantins Standard Time": "America/Araguaina",
    "E. South America Standard Time": "America/Sao_Paulo",
    "SA Eastern Standard Time": "America/Cayenne",
    "Argentina Standard Time": "America/Buenos_Aires",
    "Greenland Standard Time": "America/Godthab",
    "Montevideo Standard Time": "America/Montevideo",
    "Magallanes Standard Time": "America/Punta_Arenas",
    "Saint Pierre Standard Time": "America/Miquelon",
    "Bahia Standard Time": "America/Bahia",
    "UTC-02": "Etc/GMT+2",
    "Mid-Atlantic Standard Time": "Etc/GMT+2",
    "Azores Standard Time": "Atlantic/Azores",
    "Cape Verde Standard Time": "Atlantic/Cape_Verde",
    "UTC": "UTC",
    "GMT Standard Time": "Europe/London",
    "Greenwich Standard Time": "Atlantic/Reykjavik",
    "Sao Tome Standard Time": "Africa/Sao_Tome",
    "Morocco Standard Time": "Africa/Casablanca",
    "W. Europe Standard Time": "Europe/Amsterdam",
    "Central Europe Standard Time": "Europe/Budapest",
    "Romance Standard Time": "Europe/Paris",
    "Central European Standard Time": "Europe/Warsaw",
    "W. Central Africa Standard Time": "Africa/Lagos",
    "Jordan Standard Time": "Asia/Amman",
    "GTB Standard Time": "Europe/Bucharest",
    "Middle East Standard Time": "Asia/Beirut",
    "Egypt Standard Time": "Africa/Cairo",
    "E. Europe Standard Time": "Europe/Chisinau",
    "Syria Standard Time": "Asia/Damascus",
    "West Bank Standard Time": "Asia/Hebron",
    "South Africa Standard Time": "Africa/Johannesburg",
    "FLE Standard Time": "Europe/Kiev",
    "Israel Standard Time": "Asia/Jerusalem",
    "Kaliningrad Standard Time": "Europe/Kaliningrad",
    "Sudan Standard Time": "Africa/Khartoum",
    "Libya Standard Time": "Africa/Tripoli",
    "Namibia Standard Time": "Africa/Windhoek",
    "Arabic Standard Time": "Asia/Baghdad",
    "Turkey Standard Time": "Europe/Istanbul",
    "Arab Standard Time": "Asia/Riyadh",
    "Belarus Standard Time": "Europe/Minsk",
    "Russian Standard Time": "Europe/Moscow",
    "E. Africa Standard Time": "Africa/Nairobi",
    "Iran Standard Time": "Asia/Tehran",
    "Arabian Standard Time": "Asia/Dubai",
    "Astrakhan Standard Time": "Europe/Astrakhan",
    "Azerbaijan Standard Time": "Asia/Baku",
    "Russia Time Zone 3": "Europe/Samara",
    "Mauritius Standard Time": "Indian/Mauritius",
    "Saratov Standard Time": "Europe/Saratov",
    "Georgian Standard Time": "Asia/Tbilisi",
    "Volgograd Standard Time": "Europe/Volgograd",
    "Caucasus Standard Time": "Asia/Yerevan",
    "Afghanistan Standard Time": "Asia/Kabul",
    "West Asia Standard Time": "Asia/Tashkent",
    "Ekaterinburg Standard Time": "Asia/Yekaterinburg",
    "Pakistan Standard Time": "Asia/Karachi",
    "Qyzylorda Standard Time": "Asia/Qyzylorda",
    "India Standard Time": "Asia/Kolkata",
    "Sri Lanka Standard Time": "Asia/Colombo",
    "Nepal Standard Time": "Asia/Kathmandu",
    "Central Asia Standard Time": "Asia/Almaty",
    "Bangladesh Standard Time": "Asia/Dhaka",
    "Omsk Standard Time": "Asia/Omsk",
    "Myanmar Standard Time": "Asia/Yangon",
    "SE Asia Standard Time": "Asia/Bangkok",
    "Altai Standard Time": "Asia/Barnaul",
    "W. Mongolia Standard Time": "Asia/Hovd",
    "North Asia Standard Time": "Asia/Krasnoyarsk",
    "N. Central Asia Standard Time": "Asia/Novosibirsk",
    "Tomsk Standard Time": "Asia/Tomsk",
    "China Standard Time": "Asia/Shanghai",
    "North Asia East Standard Time": "Asia/Irkutsk",
    "Singapore Standard Time": "Asia/Singapore",
    "W. Australia Standard Time": "Australia/Perth",
    "Taipei Standard Time": "Asia/Taipei",
    "Ulaanbaatar Standard Time": "Asia/Ulaanbaatar",
    "Aus Central W. Standard Time": "Australia/Eucla",
    "Transbaikal Standard Time": "Asia/Chita",
    "Tokyo Standard Time": "Asia/Tokyo",
    "North Korea Standard Time": "Asia/Pyongyang",
    "Korea Standard Time": "Asia/Seoul",
    "Yakutsk Standard Time": "Asia/Yakutsk",
    "Cen. Australia Standard Time": "Australia/Adelaide",
    "AUS Central Standard Time": "Australia/Darwin",
    "E. Australia Standard Time": "Australia/Brisbane",
    "AUS Eastern Standard Time": "Australia/Sydney",
    "West Pacific Standard Time": "Pacific/Port_Moresby",
    "Tasmania Standard Time": "Australia/Hobart",
    "Vladivostok Standard Time": "Asia/Vladivostok",
    "Lord Howe Standard Time": "Australia/Lord_Howe",
    "Bougainville Standard Time": "Pacific/Bougainville",
    "Russia Time Zone 10": "Asia/Srednekolymsk",
    "Magadan Standard Time": "Asia/Magadan",
    "Norfolk Standard Time": "Pacific/Norfolk",
    "Sakhalin Standard Time": "Asia/Sakhalin",
    "Central Pacific Standard Time": "Pacific/Guadalcanal",
    "Russia Time Zone 11": "Asia/Kamchatka",
    "New Zealand Standard Time": "Pacific/Auckland",
    "UTC+12": "Etc/GMT-12",
    "Fiji Standard Time": "Pacific/Fiji",
    "Chatham Islands Standard Time": "Pacific/Chatham",
    "UTC+13": "Etc/GMT-13",
    "Tonga Standard Time": "Pacific/Tongatapu",
    "Samoa Standard Time": "Pacific/Apia",
    "Line Islands Standard Time": "Pacific/Kiritimati",
}


def resolve_timezone(tz_name: str) -> Optional[datetime.tzinfo]:
    """Resolve standard IANA or Windows/Exchange timezone names to a tzinfo object."""
    if not tz_name:
        return None
    cleaned = tz_name.strip().strip('"').strip("'")
    resolved = tz.gettz(cleaned)
    if resolved:
        return resolved
    mapped = WINDOWS_TO_IANA_TZ.get(cleaned)
    if mapped:
        return tz.gettz(mapped)
    return None


def unescape_ics_text(text: str) -> str:
    """Unescape RFC 5545 iCalendar escaped characters (e.g. \\, -> ,)."""
    if not text:
        return ""
    placeholder = "\uE000"
    res = text.replace(r"\\", placeholder)
    res = res.replace(r"\,", ",").replace(r"\;", ";").replace(r"\N", " ").replace(r"\n", " ")
    res = res.replace(placeholder, "\\")
    return res.strip()


class OutlookCalendarClient:
    """Client for reading Microsoft Outlook calendars and events on macOS."""

    def _unescape_ics_text(self, text: str) -> str:
        return unescape_ics_text(text)

    def __init__(self):
        self._local_tz = datetime.datetime.now().astimezone().tzinfo

    def is_available(self) -> bool:
        """Check if Microsoft Outlook application is installed and scriptable."""
        script = """
        tell application "Microsoft Outlook"
            with timeout of 10 seconds
                return name
            end timeout
        end tell
        """
        success, _ = run_applescript(script, timeout=10)
        return success

    def get_calendars(self, include_event_counts: bool = False) -> List[Dict[str, Any]]:
        """List all calendars available in Microsoft Outlook with event counts."""
        script = """
        tell application "Microsoft Outlook"
            with timeout of 60 seconds
                set calList to every calendar
                set outList to {}
                repeat with c in calList
                    set cName to name of c
                    if cName is not missing value then
                        set cId to id of c as text
                        set accName to ""
                        try
                            set accName to name of (exchange account of c)
                        on error
                            try
                                set accName to name of (account of c)
                            end try
                        end try
                        if accName is "" then set accName to "Microsoft Outlook"
                        
                        set evCount to 0
                        """ + ("""
                        try
                            set evCount to count of (calendar events of c)
                        end try
                        """ if include_event_counts else "") + """
                        
                        set end of outList to cId & "|||" & cName & "|||" & accName & "|||" & (evCount as text)
                    end if
                end repeat
                set AppleScript's text item delimiters to linefeed
                return outList as text
            end timeout
        end tell
        """
        success, output = run_applescript(script, timeout=60)
        if not success:
            raise RuntimeError(f"Failed to query Microsoft Outlook calendars: {output}")

        results = []
        lines = output.strip().splitlines() if output else []
        for line in lines:
            if not line.strip():
                continue
            parts = line.split("|||")
            if len(parts) >= 3:
                cal_id = parts[0].strip()
                cal_name = parts[1].strip()
                acc_name = parts[2].strip()
                ev_count = int(parts[3].strip()) if len(parts) >= 4 and parts[3].strip().isdigit() else None

                results.append({
                    "title": cal_name,
                    "identifier": f"outlook:{cal_id}",
                    "raw_id": cal_id,
                    "source": f"{acc_name} (Outlook)",
                    "allows_modifications": False,
                    "event_count_1yr": ev_count,
                    "provider": "outlook"
                })

        return results

    def get_calendar_by_id(self, calendar_id: str) -> Optional[Dict[str, Any]]:
        """Find calendar metadata by ID."""
        cals = self.get_calendars()
        clean_id = calendar_id.replace("outlook:", "").strip()
        for cal in cals:
            if cal["raw_id"] == clean_id or cal["identifier"] == calendar_id:
                return cal
        return None

    def get_events_by_calendar_id(
        self,
        calendar_id: str,
        start_date: datetime.datetime,
        end_date: datetime.datetime,
        chunk_days: int = 90
    ) -> List[Dict[str, Any]]:
        """Fetch and expand all single and recurring events from Outlook calendar within [start_date, end_date]."""
        clean_id = calendar_id.replace("outlook:", "").strip()
        if not clean_id.isdigit():
            raise ValueError(f"Invalid Outlook calendar ID '{calendar_id}'. Must be numeric or outlook:<num>.")

        # Ensure datetime bounds have timezone
        local_tz = self._local_tz
        s_date = start_date.astimezone(local_tz) if start_date.tzinfo else start_date.replace(tzinfo=local_tz)
        e_date = end_date.astimezone(local_tz) if end_date.tzinfo else end_date.replace(tzinfo=local_tz)

        # AppleScript query
        # 1. Non-recurring events whose start is in window
        # 2. Recurring events (fetching their icalendar data)
        days_from_now_start = int((s_date - datetime.datetime.now().astimezone()).total_seconds() / 86400) - 2
        days_from_now_end = int((e_date - datetime.datetime.now().astimezone()).total_seconds() / 86400) + 2

        script = f"""
        tell application "Microsoft Outlook"
            with timeout of 120 seconds
                set cal to calendar id {clean_id}
                set sDate to (current date) + ({days_from_now_start} * days)
                set eDate to (current date) + ({days_from_now_end} * days)
                
                -- 1. Single events
                set singleEvs to (every calendar event of cal whose is recurring is false and start time ≥ sDate and start time ≤ eDate)
                set singleOut to {{}}
                repeat with ev in singleEvs
                    set s to (start time of ev) as «class isot» as string
                    set e to (end time of ev) as «class isot» as string
                    set sub to subject of ev
                    set eid to id of ev as text
                    set isAllDay to all day flag of ev
                    set end of singleOut to eid & "|||" & s & "|||" & e & "|||" & (isAllDay as text) & "|||" & sub
                end repeat
                
                -- 2. Recurring events
                set recEvs to (every calendar event of cal whose is recurring is true)
                set recOut to {{}}
                repeat with ev in recEvs
                    set eid to id of ev as text
                    set ical to icalendar data of ev
                    set end of recOut to eid & "###EID###" & ical
                end repeat
                
                set AppleScript's text item delimiters to "###DELIM_SINGLE###"
                set singleStr to singleOut as text
                set AppleScript's text item delimiters to "###DELIM_REC###"
                set recStr to recOut as text
                
                return singleStr & "===SECTION_SPLIT===" & recStr
            end timeout
        end tell
        """

        success, output = run_applescript(script, timeout=120)
        if not success:
            raise RuntimeError(f"Failed to fetch events from Outlook calendar {calendar_id}: {output}")

        parts = output.split("===SECTION_SPLIT===")
        single_raw = parts[0].split("###DELIM_SINGLE###") if parts[0] else []
        rec_raw = parts[1].split("###DELIM_REC###") if len(parts) > 1 and parts[1] else []

        parsed_events_by_id: Dict[str, Dict[str, Any]] = {}

        # 1. Parse Single Non-Recurring Events
        for item in single_raw:
            if not item.strip():
                continue
            fields = item.split("|||")
            if len(fields) >= 5:
                eid, s_str, e_str, is_all_day_str, title = fields[0].strip(), fields[1].strip(), fields[2].strip(), fields[3].strip(), fields[4].strip()
                try:
                    # AppleScript «class isot» returns local machine wall-clock time
                    s_dt = datetime.datetime.fromisoformat(s_str).replace(tzinfo=local_tz)
                    e_dt = datetime.datetime.fromisoformat(e_str).replace(tzinfo=local_tz)
                    is_all_day = (is_all_day_str.lower() == "true")

                    if s_dt > e_date or e_dt < s_date:
                        continue

                    start_ts = int(s_dt.timestamp())
                    unique_id = f"outlook_{eid}_{start_ts}"

                    payload = {
                        "title": title or "(No Title)",
                        "start": s_dt.isoformat(),
                        "end": e_dt.isoformat(),
                        "is_all_day": is_all_day
                    }
                    chash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

                    parsed_events_by_id[unique_id] = {
                        "id": unique_id,
                        "base_id": f"outlook_{eid}",
                        "title": title or "(No Title)",
                        "start": s_dt,
                        "end": e_dt,
                        "is_all_day": is_all_day,
                        "content_hash": chash
                    }
                except Exception as e:
                    logger.debug(f"Error parsing single event {eid}: {e}")

        # 2. Parse Recurring Series from iCalendar data
        for rec_item in rec_raw:
            if not rec_item.strip():
                continue
            parts = rec_item.split("###EID###")
            eid = parts[0].strip()
            ics_blob = parts[1] if len(parts) > 1 else ""
            self._expand_ics_recurring_series(
                eid=eid,
                ics_blob=ics_blob,
                window_start=s_date,
                window_end=e_date,
                local_tz=local_tz,
                results_dict=parsed_events_by_id
            )

        sorted_events = sorted(
            parsed_events_by_id.values(),
            key=lambda x: x["start"] if x["start"] else datetime.datetime.min.astimezone()
        )
        return sorted_events

    def _expand_ics_recurring_series(
        self,
        eid: str,
        ics_blob: str,
        window_start: datetime.datetime,
        window_end: datetime.datetime,
        local_tz: datetime.tzinfo,
        results_dict: Dict[str, Dict[str, Any]]
    ):
        """Parse VCALENDAR/VEVENT stream from Outlook and expand occurrences within window."""
        unfolded = re.sub(r"\r?\n[ \t]", "", ics_blob)
        vevent_blocks = re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", unfolded, re.DOTALL)

        master_props = None
        exceptions: Dict[str, Dict[str, str]] = {}
        exdates: set = set()

        for block in vevent_blocks:
            lines = [l.strip() for l in block.strip().splitlines() if l.strip()]
            props = self._parse_vevent_props(lines)

            # Parse EXDATE lines (handling comma-separated dates and timezones)
            for line in lines:
                if line.startswith("EXDATE"):
                    if ":" in line:
                        prefix, val_part = line.split(":", 1)
                        raw_dates = val_part.split(",")
                        for raw_d in raw_dates:
                            raw_d = raw_d.strip()
                            if raw_d:
                                ex_dt, _, _ = self._parse_ics_datetime(f"{prefix}:{raw_d}", local_tz)
                                if ex_dt:
                                    exdates.add(ex_dt.isoformat())

            if "RECURRENCE-ID" in props:
                rec_id_val, _, _ = self._parse_ics_datetime(props["RECURRENCE-ID"], local_tz)
                if rec_id_val:
                    exceptions[rec_id_val.isoformat()] = props
            else:
                if master_props is None:
                    master_props = props

        if not master_props:
            return

        title = master_props.get("SUMMARY", "(No Title)")
        dtstart_str = master_props.get("DTSTART")
        dtend_str = master_props.get("DTEND")
        rrule_str = master_props.get("RRULE")

        if not dtstart_str or not rrule_str:
            return

        dtstart_local, is_all_day, event_tz = self._parse_ics_datetime(dtstart_str, local_tz)
        if not dtstart_local:
            return

        dtend_local, _, _ = self._parse_ics_datetime(dtend_str, local_tz) if dtend_str else (dtstart_local + datetime.timedelta(hours=1), is_all_day, event_tz)
        duration = (dtend_local - dtstart_local) if dtend_local else datetime.timedelta(hours=1)

        try:
            cleaned_rrule = rrule_str.strip()
            orig_tz = event_tz or local_tz

            # Expand occurrences in originating event timezone to account for Daylight Saving Time correctly
            dtstart_orig = dtstart_local.astimezone(orig_tz).replace(tzinfo=None)
            rule = rrule.rrulestr(cleaned_rrule, dtstart=dtstart_orig)

            orig_win_start = window_start.astimezone(orig_tz).replace(tzinfo=None)
            orig_win_end = window_end.astimezone(orig_tz).replace(tzinfo=None)

            occurrences = rule.between(orig_win_start, orig_win_end, inc=True)
            orig_master_title = self._unescape_ics_text(title) or "(No Title)"

            for occ in occurrences:
                # Re-attach originating timezone and convert to local machine time
                occ_orig = occ.replace(tzinfo=orig_tz)
                occ_tz = occ_orig.astimezone(local_tz)
                occ_iso = occ_tz.isoformat()

                # Check EXDATE exclusions
                if occ_iso in exdates:
                    continue

                if occ_iso in exceptions:
                    exc_props = exceptions[occ_iso]
                    if exc_props.get("STATUS", "").upper() == "CANCELLED":
                        continue

                    exc_title_raw = exc_props.get("SUMMARY", title)
                    cleaned_exc_title = self._unescape_ics_text(exc_title_raw) or "(No Title)"

                    exc_s, exc_al, _ = self._parse_ics_datetime(exc_props.get("DTSTART", dtstart_str), local_tz)
                    exc_e, _, _ = self._parse_ics_datetime(exc_props.get("DTEND", dtend_str), local_tz)
                    start_dt = exc_s if exc_s else occ_tz
                    end_dt = exc_e if exc_e else (start_dt + duration)
                    is_all_day_inst = exc_al

                    # Add visual tag if moved or updated
                    if start_dt != occ_tz:
                        if not cleaned_exc_title.startswith("[Moved]"):
                            final_title = f"[Moved] {cleaned_exc_title}"
                        else:
                            final_title = cleaned_exc_title
                    elif cleaned_exc_title != orig_master_title:
                        if not cleaned_exc_title.startswith("[Updated]") and not cleaned_exc_title.startswith("[Moved]"):
                            final_title = f"[Updated] {cleaned_exc_title}"
                        else:
                            final_title = cleaned_exc_title
                    else:
                        final_title = cleaned_exc_title
                else:
                    final_title = orig_master_title
                    start_dt = occ_tz
                    end_dt = occ_tz + duration
                    is_all_day_inst = is_all_day

                # Stable tracking ID anchored to original recurrence slot
                orig_slot_ts = int(occ_tz.timestamp())
                unique_id = f"outlook_{eid}_occ_{orig_slot_ts}"

                payload = {
                    "title": final_title,
                    "start": start_dt.isoformat(),
                    "end": end_dt.isoformat(),
                    "is_all_day": is_all_day_inst
                }
                chash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

                results_dict[unique_id] = {
                    "id": unique_id,
                    "base_id": f"outlook_{eid}",
                    "title": final_title,
                    "start": start_dt,
                    "end": end_dt,
                    "is_all_day": is_all_day_inst,
                    "content_hash": chash
                }
        except Exception as e:
            logger.debug(f"Error expanding rrule for event {eid}: {e}")

    def _parse_vevent_props(self, lines: List[str]) -> Dict[str, str]:
        """Extract property key-values from VEVENT lines."""
        props = {}
        for line in lines:
            if ":" in line:
                k, v = line.split(":", 1)
                base_k = k.split(";")[0].strip().upper()
                if base_k in ("DTSTART", "DTEND", "RECURRENCE-ID", "EXDATE", "DUE"):
                    props[base_k] = line.strip()
                else:
                    props[base_k] = v.strip()
                props[k.strip().upper()] = v.strip()
        return props

    def _parse_ics_datetime(
        self,
        val_str: str,
        default_tz: datetime.tzinfo
    ) -> Tuple[Optional[datetime.datetime], bool, Optional[datetime.tzinfo]]:
        """
        Extract datetime, all_day flag, and originating tzinfo from iCalendar DTSTART / DTEND strings.
        Returns: (datetime_in_local_tz, is_all_day, originating_tz)
        """
        tz_match = re.search(r'TZID="?([^;:"\r\n]+)"?', val_str)
        event_tz = None
        if tz_match:
            event_tz = resolve_timezone(tz_match.group(1))

        m = re.search(r"(\d{8}(?:T\d{6}Z?)?)", val_str)
        if not m:
            return None, False, None
        raw = m.group(1)
        if len(raw) == 8:
            dt = datetime.datetime.strptime(raw, "%Y%m%d")
            return dt.replace(tzinfo=default_tz), True, event_tz
        elif raw.endswith("Z"):
            dt = datetime.datetime.strptime(raw, "%Y%m%dT%H%M%SZ")
            utc_dt = dt.replace(tzinfo=datetime.timezone.utc)
            return utc_dt.astimezone(default_tz), False, datetime.timezone.utc
        else:
            dt = datetime.datetime.strptime(raw, "%Y%m%dT%H%M%S")
            if event_tz:
                local_dt = dt.replace(tzinfo=event_tz).astimezone(default_tz)
                return local_dt, False, event_tz
            else:
                return dt.replace(tzinfo=default_tz), False, default_tz

    def search_all_calendars(
        self,
        query: str,
        start_date: datetime.datetime,
        end_date: datetime.datetime
    ) -> List[Dict[str, Any]]:
        """Search across all Outlook calendars for matching events using fast native AppleScript filter."""
        clean_q = query.replace('"', '\\"').strip()
        local_tz = self._local_tz

        script = f"""
        tell application "Microsoft Outlook"
            with timeout of 60 seconds
                set matchEvs to (every calendar event whose subject contains "{clean_q}")
                set outList to {{}}
                repeat with ev in matchEvs
                    set eid to id of ev as text
                    set s to (start time of ev) as «class isot» as string
                    set e to (end time of ev) as «class isot» as string
                    set sub to subject of ev
                    set isAllDay to all day flag of ev
                    set calName to name of (calendar of ev)
                    set calId to id of (calendar of ev) as text
                    set accName to ""
                    try
                        set accName to name of (account of (calendar of ev))
                    end try
                    if accName is "" then set accName to "Outlook"
                    set end of outList to eid & "|||" & s & "|||" & e & "|||" & (isAllDay as text) & "|||" & sub & "|||" & calName & "|||" & calId & "|||" & accName
                end repeat
                set AppleScript's text item delimiters to linefeed
                return outList as text
            end timeout
        end tell
        """

        success, output = run_applescript(script, timeout=60)
        if not success:
            logger.debug(f"Outlook search failed: {output}")
            return []

        results = []
        lines = output.strip().splitlines() if output else []
        for line in lines:
            if not line.strip():
                continue
            parts = line.split("|||")
            if len(parts) >= 8:
                eid, s_str, e_str, is_all_day_str, title, cal_name, cal_id, acc_name = parts[0], parts[1], parts[2], parts[3], parts[4], parts[5], parts[6], parts[7]
                try:
                    s_dt = datetime.datetime.fromisoformat(s_str).astimezone(local_tz)
                    e_dt = datetime.datetime.fromisoformat(e_str).astimezone(local_tz)
                    is_all_day = (is_all_day_str.lower() == "true")
                    start_ts = int(s_dt.timestamp())
                    unique_id = f"outlook_{eid}_{start_ts}"

                    payload = {
                        "title": title or "(No Title)",
                        "start": s_dt.isoformat(),
                        "end": e_dt.isoformat(),
                        "is_all_day": is_all_day
                    }
                    chash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

                    results.append({
                        "id": unique_id,
                        "base_id": f"outlook_{eid}",
                        "title": title or "(No Title)",
                        "start": s_dt,
                        "end": e_dt,
                        "is_all_day": is_all_day,
                        "content_hash": chash,
                        "calendar_name": cal_name,
                        "calendar_id": f"outlook:{cal_id}",
                        "calendar_source": f"{acc_name} (Outlook)"
                    })
                except Exception as e:
                    logger.debug(f"Error parsing search result {eid}: {e}")

        return results
