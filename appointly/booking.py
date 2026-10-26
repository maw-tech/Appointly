"""Booking rules: which slots are open and how a reservation is saved safely."""
import sqlite3

from flask import current_app

from . import models, scheduling
from .db import transaction


class SlotUnavailableError(Exception):
    """Raised when a requested slot cannot be booked. str(e) is user-facing."""


def available_slots_for_day(conn, day, now, booked=None):
    """Open start times on `day`: within working hours, in the future, not booked."""
    window = scheduling.booking_window(now, current_app.config["BOOKING_WINDOW_DAYS"])
    if day not in window:
        return []
    row = models.get_day_availability(conn, day.weekday())
    if booked is None:
        booked = models.booked_times(conn, day.isoformat())
    return [
        slot
        for slot in scheduling.slots_for_availability(row)
        if slot not in booked and not scheduling.is_in_past(day, slot, now)
    ]


def availability_overview(conn, now):
    """[(date, [open slots])] for every day in the booking window (2 queries)."""
    days = scheduling.booking_window(now, current_app.config["BOOKING_WINDOW_DAYS"])
    booked = models.booked_times_between(conn, days[0].isoformat(), days[-1].isoformat())
    return [
        (day, available_slots_for_day(conn, day, now, booked.get(day.isoformat(), set())))
        for day in days
    ]


def check_slot(conn, day, start, now):
    """Raise SlotUnavailableError with a clear reason if the slot is not bookable."""
    window_days = current_app.config["BOOKING_WINDOW_DAYS"]
    if day is None or start is None or not scheduling.is_on_slot_grid(start):
        raise SlotUnavailableError("Please choose a valid date and time from the list.")
    if scheduling.is_in_past(day, start, now):
        raise SlotUnavailableError("That time has already passed. Please choose a future time.")
    if day not in scheduling.booking_window(now, window_days):
        raise SlotUnavailableError(f"Appointments can only be booked up to {window_days} days ahead.")
    row = models.get_day_availability(conn, day.weekday())
    if row is None or not row["is_working"]:
        name = scheduling.WEEKDAY_NAMES[day.weekday()]
        raise SlotUnavailableError(f"Appointments are not available on {name}s.")
    if start not in scheduling.slots_for_availability(row):
        raise SlotUnavailableError(
            f"{start} is outside working hours ({row['start_time']}-{row['end_time']})."
        )
    if start in models.booked_times(conn, day.isoformat()):
        raise SlotUnavailableError(
            "Sorry, that time slot has already been booked. Please choose another time."
        )


def book_appointment(conn, *, name, email, notes, day, start, now):
    """Validate the slot and save the reservation in a single write transaction.

    The partial UNIQUE index on (appointment_date, start_time) is the final
    safety net: if two requests race past check_slot, SQLite rejects the
    second INSERT and we report the slot as taken.
    """
    try:
        with transaction(conn):
            check_slot(conn, day, start, now)
            reference = models.insert_appointment(
                conn, name=name, email=email, notes=notes,
                day_iso=day.isoformat(), start_time=start,
            )
    except sqlite3.IntegrityError as exc:
        raise SlotUnavailableError(
            "Sorry, that time slot has already been booked. Please choose another time."
        ) from exc
    return models.get_appointment_by_reference(conn, reference)


def appointments_outside_hours(conn, now):
    """Upcoming booked appointments that no longer fit the weekly availability."""
    weekly = {row["weekday"]: row for row in models.get_weekly_availability(conn)}
    result = []
    for appt in models.upcoming_booked(conn, now.strftime("%Y-%m-%d %H:%M")):
        day = scheduling.parse_date(appt["appointment_date"])
        if appt["start_time"] not in scheduling.slots_for_availability(weekly.get(day.weekday())):
            result.append(appt)
    return result
