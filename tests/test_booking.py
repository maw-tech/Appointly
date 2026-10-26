"""Customer booking workflow, validation and double-booking prevention."""
import sqlite3

import pytest

from appointly import booking, models
from conftest import MONDAY, SATURDAY, SUNDAY, TUESDAY, appointment_rows, book


# ----- viewing availability --------------------------------------------------

def test_home_page_shows_weekly_hours(client):
    page = client.get("/").get_data(as_text=True)
    assert "Weekly hours" in page
    assert "Sunday" in page and "Closed" in page


def test_booking_page_hides_past_slots_today(client):
    # Frozen time is Monday 10:15, so 10:00 has passed and 10:30 is the first open slot.
    page = client.get(f"/book?date={MONDAY}").get_data(as_text=True)
    assert f"date={MONDAY}&amp;time=10:30" in page
    assert f"date={MONDAY}&amp;time=10:00" not in page
    assert f"date={MONDAY}&amp;time=09:00" not in page


def test_booking_page_lists_all_slots_for_future_day(client):
    page = client.get(f"/book?date={TUESDAY}").get_data(as_text=True)
    assert page.count(f"date={TUESDAY}&amp;time=") == 16  # 09:00-17:00


def test_saturday_uses_its_own_hours(client):
    page = client.get(f"/book?date={SATURDAY}").get_data(as_text=True)
    assert f"date={SATURDAY}&amp;time=10:00" in page
    assert f"date={SATURDAY}&amp;time=13:30" in page
    assert f"date={SATURDAY}&amp;time=14:00" not in page


def test_booked_slot_is_not_offered(client):
    book(client, time="11:00")
    page = client.get(f"/book?date={TUESDAY}").get_data(as_text=True)
    assert f"date={TUESDAY}&amp;time=11:00" not in page
    assert page.count(f"date={TUESDAY}&amp;time=") == 15


def test_details_form_for_open_slot(client):
    response = client.get(f"/book/details?date={TUESDAY}&time=10:00")
    assert response.status_code == 200
    assert "Your details" in response.get_data(as_text=True)


def test_details_form_for_taken_slot_redirects_with_error(client):
    book(client, time="10:00")
    response = client.get(f"/book/details?date={TUESDAY}&time=10:00", follow_redirects=True)
    assert "already been booked" in response.get_data(as_text=True)


# ----- successful booking ------------------------------------------------------

def test_successful_booking_shows_confirmation(client, conn):
    response = book(client, notes="Calculus homework")
    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "You're booked!" in page
    assert "Alex Morgan" in page
    assert "alex.morgan@example.com" in page
    assert "10:00 AM" in page

    rows = appointment_rows(conn)
    assert len(rows) == 1
    row = rows[0]
    assert (row["appointment_date"], row["start_time"], row["status"]) == (TUESDAY, "10:00", "booked")
    assert row["notes"] == "Calculus homework"
    assert row["reference"] in page


def test_booking_redirects_to_reference_url(client, conn):
    response = book(client, follow=False)
    reference = appointment_rows(conn)[0]["reference"]
    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/booking/{reference}")


def test_unknown_confirmation_reference_is_404(client):
    assert client.get("/booking/DOESNOTEXIST").status_code == 404


def test_customer_input_is_html_escaped(client):
    book(client, notes="<script>alert(1)</script>")
    page = client.get(f"/booking/{_only_reference(client)}").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page


def _only_reference(client):
    with client.application.app_context():
        from appointly.db import get_db
        return get_db().execute("SELECT reference FROM appointments").fetchone()[0]


# ----- double booking -------------------------------------------------------

def test_second_booking_for_same_slot_is_rejected(client, conn):
    book(client, name="Alex Morgan", email="alex@example.com")
    response = book(client, name="Blake Chen", email="blake@example.com")
    page = response.get_data(as_text=True)
    assert "already been booked" in page
    rows = appointment_rows(conn)
    assert len(rows) == 1
    assert rows[0]["customer_name"] == "Alex Morgan"


def test_different_slots_can_both_be_booked(client, conn):
    book(client, time="10:00")
    book(client, time="10:30", name="Blake Chen", email="blake@example.com")
    assert len(appointment_rows(conn)) == 2


def test_database_unique_index_blocks_duplicate_active_bookings(conn):
    """The constraint is enforced by SQLite itself, not just application code."""
    sql = ("INSERT INTO appointments (reference, customer_name, customer_email, appointment_date, "
           "start_time, status, created_at) VALUES (?, 'Test User', 't@example.com', ?, '10:00', ?, 'now')")
    conn.execute(sql, ("REF1", TUESDAY, "booked"))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(sql, ("REF2", TUESDAY, "booked"))
    # Cancelled rows are outside the partial index, so they do not block a slot.
    conn.execute("UPDATE appointments SET status = 'cancelled' WHERE reference = 'REF1'")
    conn.execute(sql, ("REF3", TUESDAY, "booked"))
    conn.execute(sql, ("REF4", TUESDAY, "cancelled"))


def test_race_condition_is_caught_by_database_constraint(app, conn, monkeypatch):
    """Simulate two requests that both passed the availability check."""
    from conftest import FIXED_NOW
    from datetime import date

    monkeypatch.setattr(booking, "check_slot", lambda *args, **kwargs: None)
    day = date.fromisoformat(TUESDAY)
    with app.app_context():
        booking.book_appointment(conn, name="Alex Morgan", email="a@example.com", notes="",
                                 day=day, start="10:00", now=FIXED_NOW)
        with pytest.raises(booking.SlotUnavailableError, match="already been booked"):
            booking.book_appointment(conn, name="Blake Chen", email="b@example.com", notes="",
                                     day=day, start="10:00", now=FIXED_NOW)
    assert len(appointment_rows(conn)) == 1


# ----- rejected slots ---------------------------------------------------------

@pytest.mark.parametrize(
    "date, time, message",
    [
        (MONDAY, "09:00", "already passed"),           # earlier today
        ("2026-10-30", "10:00", "already passed"),      # a past day
        (MONDAY, "18:00", "outside working hours"),     # after hours
        (TUESDAY, "08:30", "outside working hours"),    # before hours
        (TUESDAY, "16:45", "valid date and time"),      # not on the 30-minute grid
        (SATURDAY, "14:00", "outside working hours"),   # Saturday closes at 14:00
        (SUNDAY, "10:00", "not available on Sundays"),  # closed day
        ("2026-11-16", "10:00", "up to 14 days"),       # beyond the booking window
        ("2026-02-30", "10:00", "valid date and time"),  # impossible date
        (TUESDAY, "25:00", "valid date and time"),      # impossible time
        ("", "", "valid date and time"),                # missing values
    ],
)
def test_invalid_slots_are_rejected(client, conn, date, time, message):
    response = book(client, date=date, time=time)
    assert message in response.get_data(as_text=True)
    assert appointment_rows(conn) == []


# ----- customer field validation ---------------------------------------------

@pytest.mark.parametrize(
    "field, value, message",
    [
        ("name", "", "Please enter your name."),
        ("name", "R2-D2", "Name may only contain"),
        ("email", "", "Please enter your email address."),
        ("email", "not-an-email", "valid email address"),
        ("notes", "x" * 501, "500 characters or fewer"),
    ],
)
def test_invalid_customer_fields_are_rejected(client, conn, field, value, message):
    data = {"name": "Alex Morgan", "email": "alex@example.com", "notes": ""}
    data[field] = value
    response = book(client, **data)
    page = response.get_data(as_text=True)
    assert response.status_code == 400
    assert message in page
    assert "is-invalid" in page
    assert appointment_rows(conn) == []


def test_valid_fields_are_kept_when_form_is_redisplayed(client):
    page = book(client, name="Alex Morgan", email="bad").get_data(as_text=True)
    assert 'value="Alex Morgan"' in page


def test_stored_email_is_normalised(client, conn):
    book(client, email="  Alex.Morgan@Example.COM ")
    assert appointment_rows(conn)[0]["customer_email"] == "alex.morgan@example.com"


def test_availability_overview_counts(app, conn):
    from conftest import FIXED_NOW

    with app.app_context():
        overview = dict(booking.availability_overview(conn, FIXED_NOW))
    by_iso = {day.isoformat(): slots for day, slots in overview.items()}
    assert len(by_iso[MONDAY]) == 13  # 10:30 .. 16:30
    assert len(by_iso[SATURDAY]) == 8
    assert by_iso[SUNDAY] == []
    models.insert_appointment(conn, name="A B", email="a@example.com", notes="",
                              day_iso=TUESDAY, start_time="09:00")
    with app.app_context():
        overview = {d.isoformat(): s for d, s in booking.availability_overview(conn, FIXED_NOW)}
    assert "09:00" not in overview[TUESDAY]
