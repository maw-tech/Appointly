"""Shared pytest fixtures.

Every test gets its own temporary SQLite file and a frozen "current time"
of Monday 2 November 2026, 10:15 in America/New_York, so results never
depend on when the tests are run.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from appointly import create_app, models, scheduling
from appointly.db import connect

TZ = ZoneInfo("America/New_York")
FIXED_NOW = datetime(2026, 11, 2, 10, 15, tzinfo=TZ)  # a Monday
MONDAY = "2026-11-02"
TUESDAY = "2026-11-03"
SATURDAY = "2026-11-07"
SUNDAY = "2026-11-08"

ADMIN_USER = "admin"
ADMIN_PASSWORD = "test-password-123"


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.sqlite3")


@pytest.fixture
def make_app(db_path, monkeypatch):
    monkeypatch.setattr(scheduling, "current_time", lambda: FIXED_NOW)

    def factory(**overrides):
        config = {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "DATABASE": db_path,
            "TIMEZONE": "America/New_York",
            "BOOKING_WINDOW_DAYS": 14,
            "CSRF_ENABLED": False,
        }
        config.update(overrides)
        return create_app(config)

    return factory


@pytest.fixture
def app(make_app):
    return make_app()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def conn(db_path, app):
    connection = connect(db_path)
    yield connection
    connection.close()


@pytest.fixture
def admin_client(app, conn):
    models.upsert_admin(conn, ADMIN_USER, ADMIN_PASSWORD)
    client = app.test_client()
    response = client.post("/admin/login", data={"username": ADMIN_USER, "password": ADMIN_PASSWORD})
    assert response.status_code == 302
    return client


def book(client, date=TUESDAY, time="10:00", name="Alex Morgan",
         email="alex.morgan@example.com", notes="", follow=True):
    """Submit the booking form."""
    return client.post(
        "/book",
        data={"date": date, "time": time, "name": name, "email": email, "notes": notes},
        follow_redirects=follow,
    )


def appointment_rows(conn):
    return conn.execute("SELECT * FROM appointments ORDER BY id").fetchall()
