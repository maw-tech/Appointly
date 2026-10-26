"""CSRF protection, security headers, persistence and CLI commands."""
from appointly import create_app, models
from appointly.db import connect
from conftest import ADMIN_PASSWORD, ADMIN_USER, TUESDAY, appointment_rows, book


def _csrf(client):
    client.get(f"/book/details?date={TUESDAY}&time=10:00")  # renders a form
    with client.session_transaction() as sess:
        return sess["_csrf_token"]


def test_post_without_csrf_token_is_rejected(make_app, db_path):
    client = make_app(CSRF_ENABLED=True).test_client()
    response = book(client, follow=False)
    assert response.status_code == 400
    assert "form session expired" in response.get_data(as_text=True)
    conn = connect(db_path)
    assert appointment_rows(conn) == []
    conn.close()


def test_post_with_wrong_csrf_token_is_rejected(make_app):
    client = make_app(CSRF_ENABLED=True).test_client()
    _csrf(client)
    response = client.post("/book", data={"csrf_token": "wrong", "date": TUESDAY, "time": "10:00",
                                          "name": "Alex Morgan", "email": "a@example.com"})
    assert response.status_code == 400


def test_post_with_valid_csrf_token_succeeds(make_app):
    client = make_app(CSRF_ENABLED=True).test_client()
    token = _csrf(client)
    response = client.post("/book", data={"csrf_token": token, "date": TUESDAY, "time": "10:00",
                                          "name": "Alex Morgan", "email": "a@example.com"})
    assert response.status_code == 302
    assert "/booking/" in response.headers["Location"]


def test_admin_login_requires_csrf_token(make_app, db_path):
    app = make_app(CSRF_ENABLED=True)
    conn = connect(db_path)
    models.upsert_admin(conn, ADMIN_USER, ADMIN_PASSWORD)
    conn.close()
    client = app.test_client()
    response = client.post("/admin/login", data={"username": ADMIN_USER, "password": ADMIN_PASSWORD})
    assert response.status_code == 400


def test_forms_include_csrf_token(client):
    page = client.get(f"/book/details?date={TUESDAY}&time=10:00").get_data(as_text=True)
    assert 'name="csrf_token"' in page


def test_security_headers(client):
    response = client.get("/")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"


def test_session_cookie_is_httponly(admin_client):
    cookie = admin_client.get_cookie("session")
    assert cookie is not None and cookie.http_only


def test_bookings_survive_application_restart(make_app, db_path):
    first = make_app()
    book(first.test_client(), name="Alex Morgan", email="alex@example.com")

    # A brand-new application instance reading the same SQLite file.
    second = make_app()
    page = second.test_client().get(f"/book?date={TUESDAY}").get_data(as_text=True)
    assert f"date={TUESDAY}&amp;time=10:00" not in page
    conn = connect(db_path)
    rows = appointment_rows(conn)
    conn.close()
    assert [(r["customer_name"], r["status"]) for r in rows] == [("Alex Morgan", "booked")]


def test_restart_does_not_overwrite_custom_availability(make_app, db_path):
    make_app()
    conn = connect(db_path)
    conn.execute("UPDATE availability SET start_time = '11:00' WHERE weekday = 0")
    conn.close()
    make_app()  # schema is re-applied on start-up
    conn = connect(db_path)
    assert models.get_day_availability(conn, 0)["start_time"] == "11:00"
    conn.close()


def test_init_db_command(make_app, db_path):
    result = make_app().test_cli_runner().invoke(args=["init-db"])
    assert result.exit_code == 0
    assert "Database ready" in result.output
    conn = connect(db_path)
    assert len(models.get_weekly_availability(conn)) == 7
    conn.close()


def test_create_admin_command(make_app, db_path):
    runner = make_app().test_cli_runner()
    result = runner.invoke(args=["create-admin", "--username", "owner", "--password", "s3cret-pass"])
    assert result.exit_code == 0, result.output
    assert "created" in result.output
    result = runner.invoke(args=["create-admin", "--username", "owner", "--password", "new-pass-123"])
    assert "password updated" in result.output
    conn = connect(db_path)
    assert models.verify_admin(conn, "owner", "new-pass-123") is not None
    assert models.verify_admin(conn, "owner", "s3cret-pass") is None
    conn.close()


def test_create_admin_rejects_short_password(make_app):
    result = make_app().test_cli_runner().invoke(args=["create-admin", "--username", "owner", "--password", "short"])
    assert result.exit_code != 0
    assert "at least 8 characters" in result.output


def test_seed_demo_command_creates_fictional_bookings(make_app, db_path):
    result = make_app().test_cli_runner().invoke(args=["seed-demo"])
    assert result.exit_code == 0, result.output
    assert "Added 4 demo appointment(s)" in result.output
    conn = connect(db_path)
    rows = appointment_rows(conn)
    conn.close()
    assert len(rows) == 4
    assert all(r["customer_email"].endswith(("@example.com", "@example.org")) for r in rows)


def test_invalid_timezone_fails_fast(db_path):
    import pytest

    with pytest.raises(RuntimeError, match="Invalid APPOINTLY_TIMEZONE"):
        create_app({"DATABASE": db_path, "SECRET_KEY": "x", "TIMEZONE": "Mars/Olympus"})
