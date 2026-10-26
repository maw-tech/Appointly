"""Administrator login, dashboard, cancellation and availability management."""
import re

import pytest

from appointly import models
from conftest import ADMIN_PASSWORD, ADMIN_USER, MONDAY, TUESDAY, appointment_rows, book


def availability_form(**changes):
    """Build a full availability form from the demo defaults, then apply changes."""
    form = {}
    defaults = {0: ("09:00", "17:00"), 1: ("09:00", "17:00"), 2: ("09:00", "17:00"),
                3: ("09:00", "17:00"), 4: ("09:00", "17:00"), 5: ("10:00", "14:00")}
    for day in range(7):
        start, end = defaults.get(day, ("09:00", "17:00"))
        form[f"start_{day}"], form[f"end_{day}"] = start, end
        if day in defaults:
            form[f"working_{day}"] = "on"
    for key, value in changes.items():
        if value is None:
            form.pop(key, None)
        else:
            form[key] = value
    return form


# ----- access control -------------------------------------------------------

@pytest.mark.parametrize("method, url", [
    ("get", "/admin/"),
    ("get", "/admin/availability"),
    ("post", "/admin/availability"),
    ("post", "/admin/appointments/1/cancel"),
])
def test_admin_routes_require_login(client, method, url):
    response = getattr(client, method)(url)
    assert response.status_code == 302
    assert "/admin/login" in response.headers["Location"]


def test_login_page_explains_missing_admin(client):
    assert "No administrator account exists yet" in client.get("/admin/login").get_data(as_text=True)


def test_wrong_password_is_rejected(client, conn):
    models.upsert_admin(conn, ADMIN_USER, ADMIN_PASSWORD)
    response = client.post("/admin/login", data={"username": ADMIN_USER, "password": "wrong-password"})
    assert response.status_code == 401
    assert "Incorrect username or password" in response.get_data(as_text=True)
    assert client.get("/admin/").status_code == 302


def test_unknown_user_is_rejected(client):
    response = client.post("/admin/login", data={"username": "nobody", "password": "whatever123"})
    assert response.status_code == 401


def test_password_is_stored_hashed(conn):
    models.upsert_admin(conn, ADMIN_USER, ADMIN_PASSWORD)
    stored = conn.execute("SELECT password_hash FROM admin_users").fetchone()[0]
    assert ADMIN_PASSWORD not in stored
    assert stored.startswith(("scrypt:", "pbkdf2:"))


def test_login_redirects_to_safe_next_only(client, conn):
    models.upsert_admin(conn, ADMIN_USER, ADMIN_PASSWORD)
    creds = {"username": ADMIN_USER, "password": ADMIN_PASSWORD}
    response = client.post("/admin/login?next=//evil.example.com/", data=creds)
    assert response.headers["Location"] == "/admin/"
    client.post("/admin/logout")
    response = client.post("/admin/login?next=/admin/availability", data=creds)
    assert response.headers["Location"] == "/admin/availability"


def test_logout_ends_session(admin_client):
    assert admin_client.get("/admin/").status_code == 200
    admin_client.post("/admin/logout")
    assert admin_client.get("/admin/").status_code == 302


# ----- dashboard ------------------------------------------------------------

def test_dashboard_lists_booking_details(admin_client):
    book(admin_client, name="Jordan Rivera", email="jordan@example.com", time="14:00")
    page = admin_client.get("/admin/").get_data(as_text=True)
    assert "Jordan Rivera" in page
    assert "jordan@example.com" in page
    assert "Tue Nov 3" in page
    assert "2:00 PM" in page
    assert "Booked" in page


def test_dashboard_views_filter_by_status(admin_client, conn):
    book(admin_client, name="Alex Morgan", email="a@example.com", time="10:00")
    book(admin_client, name="Blake Chen", email="b@example.com", time="11:00")
    blake = appointment_rows(conn)[1]
    admin_client.post(f"/admin/appointments/{blake['id']}/cancel", follow_redirects=True)

    upcoming = admin_client.get("/admin/?view=upcoming").get_data(as_text=True)
    cancelled = admin_client.get("/admin/?view=cancelled").get_data(as_text=True)
    everything = admin_client.get("/admin/?view=all").get_data(as_text=True)
    assert "Alex Morgan" in upcoming and "Blake Chen" not in upcoming
    assert "Blake Chen" in cancelled and "Alex Morgan" not in cancelled
    assert "Alex Morgan" in everything and "Blake Chen" in everything


def test_dashboard_past_view(admin_client, conn):
    # Inserted directly because customers cannot book past slots.
    models.insert_appointment(conn, name="Past Person", email="p@example.com", notes="",
                              day_iso=MONDAY, start_time="09:00")
    assert "Past Person" in admin_client.get("/admin/?view=past").get_data(as_text=True)
    assert "Past Person" not in admin_client.get("/admin/?view=upcoming").get_data(as_text=True)


def test_dashboard_search(admin_client):
    book(admin_client, name="Alex Morgan", email="a@example.com", time="10:00")
    book(admin_client, name="Blake Chen", email="b@example.com", time="11:00")
    page = admin_client.get("/admin/?q=blake").get_data(as_text=True)
    assert "Blake Chen" in page and "Alex Morgan" not in page
    # LIKE wildcards are treated literally
    assert "Alex Morgan" not in admin_client.get("/admin/?q=%25").get_data(as_text=True)


# ----- cancellation ---------------------------------------------------------

def test_cancel_releases_slot_for_new_booking(admin_client, conn):
    book(admin_client, name="Alex Morgan", email="a@example.com")
    appt = appointment_rows(conn)[0]

    response = admin_client.post(f"/admin/appointments/{appt['id']}/cancel", follow_redirects=True)
    assert "The slot is available again" in response.get_data(as_text=True)
    row = appointment_rows(conn)[0]
    assert row["status"] == "cancelled"
    assert row["cancelled_at"] is not None

    page = admin_client.get(f"/book?date={TUESDAY}").get_data(as_text=True)
    assert f"date={TUESDAY}&amp;time=10:00" in page

    response = book(admin_client, name="Blake Chen", email="b@example.com")
    assert "You're booked!" in response.get_data(as_text=True)
    statuses = [(r["customer_name"], r["status"]) for r in appointment_rows(conn)]
    assert statuses == [("Alex Morgan", "cancelled"), ("Blake Chen", "booked")]


def test_cancel_twice_is_harmless(admin_client, conn):
    book(admin_client)
    appt_id = appointment_rows(conn)[0]["id"]
    admin_client.post(f"/admin/appointments/{appt_id}/cancel")
    response = admin_client.post(f"/admin/appointments/{appt_id}/cancel", follow_redirects=True)
    assert "already cancelled" in response.get_data(as_text=True)


def test_cancel_unknown_appointment_is_404(admin_client):
    assert admin_client.post("/admin/appointments/999/cancel").status_code == 404


def test_cancel_requires_post(admin_client, conn):
    book(admin_client)
    appt_id = appointment_rows(conn)[0]["id"]
    assert admin_client.get(f"/admin/appointments/{appt_id}/cancel").status_code == 405
    assert appointment_rows(conn)[0]["status"] == "booked"


def test_confirmation_page_shows_cancelled_status(admin_client, conn):
    book(admin_client)
    appt = appointment_rows(conn)[0]
    admin_client.post(f"/admin/appointments/{appt['id']}/cancel")
    page = admin_client.get(f"/booking/{appt['reference']}").get_data(as_text=True)
    assert "Appointment cancelled" in page


# ----- availability ---------------------------------------------------------

def test_availability_page_shows_current_hours(admin_client):
    page = admin_client.get("/admin/availability").get_data(as_text=True)
    assert "Weekly availability" in page
    monday = re.search(r'<input[^>]*name="working_0"[^>]*>', page).group(0)
    sunday = re.search(r'<input[^>]*name="working_6"[^>]*>', page).group(0)
    assert "checked" in monday
    assert "checked" not in sunday


def test_update_availability_changes_bookable_slots(admin_client, conn):
    form = availability_form(working_1=None, start_0="12:00", end_0="15:00")  # Tuesday off
    response = admin_client.post("/admin/availability", data=form, follow_redirects=True)
    assert "Weekly availability saved" in response.get_data(as_text=True)

    tuesday = models.get_day_availability(conn, 1)
    monday = models.get_day_availability(conn, 0)
    assert tuesday["is_working"] == 0
    assert (monday["start_time"], monday["end_time"]) == ("12:00", "15:00")

    # Customers can no longer book Tuesday, and Monday only between 12:00 and 15:00.
    assert "not available on Tuesdays" in book(admin_client, date=TUESDAY).get_data(as_text=True)
    page = admin_client.get(f"/book?date={MONDAY}").get_data(as_text=True)
    assert page.count(f"date={MONDAY}&amp;time=") == 6
    assert "outside working hours" in book(admin_client, date=MONDAY, time="11:00").get_data(as_text=True)
    assert appointment_rows(conn) == []


def test_sunday_can_be_opened(admin_client):
    form = availability_form(working_6="on", start_6="13:00", end_6="15:00")
    admin_client.post("/admin/availability", data=form)
    page = admin_client.get("/book?date=2026-11-08").get_data(as_text=True)
    assert page.count("date=2026-11-08&amp;time=") == 4


@pytest.mark.parametrize("changes, message", [
    ({"start_0": "17:00", "end_0": "09:00"}, "end time must be later"),
    ({"start_0": "10:00", "end_0": "10:00"}, "end time must be later"),
    ({"start_0": "10:15"}, "choose start and end times"),
    ({"end_2": "nonsense"}, "choose start and end times"),
])
def test_invalid_availability_is_not_saved(admin_client, conn, changes, message):
    response = admin_client.post("/admin/availability", data=availability_form(**changes))
    assert response.status_code == 400
    assert message in response.get_data(as_text=True)
    monday = models.get_day_availability(conn, 0)
    assert (monday["start_time"], monday["end_time"]) == ("09:00", "17:00")


def test_availability_change_warns_about_existing_bookings(admin_client, conn):
    book(admin_client, date=TUESDAY, time="16:00")
    form = availability_form(start_1="09:00", end_1="12:00")
    page = admin_client.post("/admin/availability", data=form, follow_redirects=True).get_data(as_text=True)
    assert "1 upcoming appointment(s) now fall outside your working hours" in page
    # The existing booking is kept and flagged on the dashboard.
    assert appointment_rows(conn)[0]["status"] == "booked"
    assert "Outside hours" in admin_client.get("/admin/").get_data(as_text=True)
