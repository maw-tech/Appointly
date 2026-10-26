"""Unit tests for the pure time/slot helpers and input validation."""
from datetime import date, datetime

import pytest

from appointly import scheduling, validation
from conftest import FIXED_NOW, TZ


def test_day_slots_are_thirty_minutes_and_fit_inside_hours():
    slots = scheduling.day_slots("09:00", "17:00")
    assert len(slots) == 16
    assert slots[0] == "09:00"
    assert slots[1] == "09:30"
    assert slots[-1] == "16:30"  # 16:30-17:00 is the last full slot


def test_single_slot_day():
    assert scheduling.day_slots("09:00", "09:30") == ["09:00"]


def test_closed_day_has_no_slots():
    row = {"is_working": 0, "start_time": "09:00", "end_time": "17:00"}
    assert scheduling.slots_for_availability(row) == []


@pytest.mark.parametrize("value", ["9:00", "24:00", "12:60", "ab:cd", "", None, "10:00:00"])
def test_parse_time_rejects_invalid_values(value):
    assert scheduling.parse_time(value) is None


@pytest.mark.parametrize("value", ["2026-13-01", "2026-02-30", "2026-1-1", "tomorrow", "", None])
def test_parse_date_rejects_invalid_values(value):
    assert scheduling.parse_date(value) is None


def test_parse_date_accepts_iso_date():
    assert scheduling.parse_date("2026-11-03") == date(2026, 11, 3)


def test_slot_grid():
    assert scheduling.is_on_slot_grid("10:30")
    assert not scheduling.is_on_slot_grid("10:15")


def test_is_in_past():
    today = FIXED_NOW.date()
    assert scheduling.is_in_past(today, "10:00", FIXED_NOW)
    assert not scheduling.is_in_past(today, "10:30", FIXED_NOW)


def test_slot_starting_exactly_now_counts_as_past():
    now = datetime(2026, 11, 2, 10, 30, tzinfo=TZ)
    assert scheduling.is_in_past(now.date(), "10:30", now)


def test_booking_window_starts_today():
    days = scheduling.booking_window(FIXED_NOW, 14)
    assert len(days) == 14
    assert days[0] == FIXED_NOW.date()
    assert days[-1] == date(2026, 11, 15)


def test_end_time_of():
    assert scheduling.end_time_of("16:30") == "17:00"


@pytest.mark.parametrize("name", ["Alex Morgan", "Mary-Jane O'Neil", "J. R. Smith", "Zoë Ölander"])
def test_valid_names(name):
    assert validation.clean_name(name)[1] is None


@pytest.mark.parametrize("name", ["", "  ", "A", "<script>", "Robert1", "x" * 81])
def test_invalid_names(name):
    assert validation.clean_name(name)[1] is not None


def test_name_whitespace_is_collapsed():
    assert validation.clean_name("  Alex    Morgan ")[0] == "Alex Morgan"


@pytest.mark.parametrize("email", ["alex@example.com", "first.last+tag@sub.example.org"])
def test_valid_emails(email):
    assert validation.clean_email(email)[1] is None


@pytest.mark.parametrize("email", ["", "alex", "alex@", "@example.com", "alex@example", "a..b@example.com",
                                   "alex @example.com"])
def test_invalid_emails(email):
    assert validation.clean_email(email)[1] is not None


def test_email_is_lowercased():
    assert validation.clean_email(" Alex@Example.COM ")[0] == "alex@example.com"


def test_notes_length_limit():
    assert validation.clean_notes("x" * 500)[1] is None
    assert validation.clean_notes("x" * 501)[1] is not None
