"""Pure date/time logic: timezone, 30-minute slots and the booking window.

Nothing in this module touches the database, which keeps it easy to test.
"""
import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from flask import current_app

SLOT_MINUTES = 30
WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def get_timezone():
    return ZoneInfo(current_app.config["TIMEZONE"])


def current_time():
    """The current time in the provider's timezone (tests replace this)."""
    return datetime.now(get_timezone())


# ----- parsing / formatting -------------------------------------------------

def parse_date(value):
    """Parse a strict YYYY-MM-DD string. Returns a date or None."""
    if not isinstance(value, str) or not _ISO_DATE.match(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def parse_time(value):
    """Parse a strict 24-hour HH:MM string. Returns a time or None."""
    if not isinstance(value, str):
        return None
    match = _HHMM.match(value)
    if not match:
        return None
    return time(int(match.group(1)), int(match.group(2)))


def to_minutes(hhmm):
    t = parse_time(hhmm)
    return t.hour * 60 + t.minute


def from_minutes(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def is_on_slot_grid(hhmm):
    t = parse_time(hhmm)
    return t is not None and t.minute % SLOT_MINUTES == 0


def time_options():
    """All valid slot boundaries for the availability form: 00:00 ... 23:30."""
    return [from_minutes(m) for m in range(0, 24 * 60, SLOT_MINUTES)]


def end_time_of(hhmm):
    return from_minutes(to_minutes(hhmm) + SLOT_MINUTES)


# ----- slots ----------------------------------------------------------------

def day_slots(start_time, end_time):
    """Start times of every full 30-minute slot between start and end."""
    start, end = to_minutes(start_time), to_minutes(end_time)
    return [from_minutes(m) for m in range(start, end - SLOT_MINUTES + 1, SLOT_MINUTES)]


def slots_for_availability(row):
    """Slots for one availability row (or an empty list on a day off)."""
    if row is None or not row["is_working"]:
        return []
    return day_slots(row["start_time"], row["end_time"])


def slot_start(day, hhmm, tz):
    return datetime.combine(day, parse_time(hhmm), tzinfo=tz)


def is_in_past(day, hhmm, now):
    """True when the slot starts at or before `now` (an aware datetime)."""
    return slot_start(day, hhmm, now.tzinfo) <= now


def booking_window(now, days):
    """Dates customers may book: today plus the following days-1 days."""
    today = now.date()
    return [today + timedelta(days=i) for i in range(days)]
