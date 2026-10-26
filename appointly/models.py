"""Data access functions. Every query uses ? placeholders (parameterised SQL)."""
import secrets
from datetime import datetime, timezone

from werkzeug.security import check_password_hash, generate_password_hash


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ----- availability ---------------------------------------------------------

def get_weekly_availability(conn):
    """Return a list of 7 rows ordered Monday..Sunday."""
    return conn.execute(
        "SELECT weekday, is_working, start_time, end_time FROM availability ORDER BY weekday"
    ).fetchall()


def get_day_availability(conn, weekday):
    return conn.execute(
        "SELECT weekday, is_working, start_time, end_time FROM availability WHERE weekday = ?",
        (weekday,),
    ).fetchone()


def save_weekly_availability(conn, days):
    """`days` is a list of dicts with weekday, is_working, start_time, end_time."""
    conn.executemany(
        "INSERT INTO availability (weekday, is_working, start_time, end_time) "
        "VALUES (:weekday, :is_working, :start_time, :end_time) "
        "ON CONFLICT(weekday) DO UPDATE SET is_working = excluded.is_working, "
        "start_time = excluded.start_time, end_time = excluded.end_time",
        days,
    )


# ----- appointments ---------------------------------------------------------

def booked_times(conn, day_iso):
    rows = conn.execute(
        "SELECT start_time FROM appointments WHERE appointment_date = ? AND status = 'booked'",
        (day_iso,),
    ).fetchall()
    return {row["start_time"] for row in rows}


def booked_times_between(conn, first_iso, last_iso):
    """Map of date -> set of booked start times for a date range (inclusive)."""
    rows = conn.execute(
        "SELECT appointment_date, start_time FROM appointments "
        "WHERE status = 'booked' AND appointment_date BETWEEN ? AND ?",
        (first_iso, last_iso),
    ).fetchall()
    result = {}
    for row in rows:
        result.setdefault(row["appointment_date"], set()).add(row["start_time"])
    return result


def insert_appointment(conn, *, name, email, notes, day_iso, start_time):
    reference = secrets.token_hex(6).upper()
    conn.execute(
        "INSERT INTO appointments (reference, customer_name, customer_email, notes, "
        "appointment_date, start_time, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 'booked', ?)",
        (reference, name, email, notes, day_iso, start_time, utc_now_iso()),
    )
    return reference


def get_appointment(conn, appointment_id):
    return conn.execute("SELECT * FROM appointments WHERE id = ?", (appointment_id,)).fetchone()


def get_appointment_by_reference(conn, reference):
    return conn.execute(
        "SELECT * FROM appointments WHERE reference = ?", (reference,)
    ).fetchone()


def cancel_appointment(conn, appointment_id):
    """Mark a booked appointment as cancelled. Returns True if a row changed."""
    cur = conn.execute(
        "UPDATE appointments SET status = 'cancelled', cancelled_at = ? "
        "WHERE id = ? AND status = 'booked'",
        (utc_now_iso(), appointment_id),
    )
    return cur.rowcount == 1


VIEWS = ("upcoming", "past", "cancelled", "all")


def list_appointments(conn, view, now_local, search=""):
    """List appointments for the admin dashboard.

    `now_local` is "YYYY-MM-DD HH:MM" in provider time; comparing text works
    because both parts are zero-padded.
    """
    slot = "(appointment_date || ' ' || start_time)"
    clauses, params = [], []
    if view == "upcoming":
        clauses.append(f"status = 'booked' AND {slot} >= ?")
        params.append(now_local)
        order = "appointment_date ASC, start_time ASC"
    elif view == "past":
        clauses.append(f"status = 'booked' AND {slot} < ?")
        params.append(now_local)
        order = "appointment_date DESC, start_time DESC"
    elif view == "cancelled":
        clauses.append("status = 'cancelled'")
        order = "appointment_date DESC, start_time DESC"
    else:
        order = "appointment_date DESC, start_time DESC"

    if search:
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        clauses.append("(customer_name LIKE ? ESCAPE '\\' OR customer_email LIKE ? ESCAPE '\\')")
        params.extend([f"%{escaped}%", f"%{escaped}%"])

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return conn.execute(f"SELECT * FROM appointments {where} ORDER BY {order}", params).fetchall()


def dashboard_counts(conn, now_local, today_iso):
    slot = "(appointment_date || ' ' || start_time)"
    row = conn.execute(
        "SELECT "
        f"SUM(CASE WHEN status = 'booked' AND {slot} >= ? THEN 1 ELSE 0 END) AS upcoming, "
        "SUM(CASE WHEN status = 'booked' AND appointment_date = ? THEN 1 ELSE 0 END) AS today, "
        "SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) AS cancelled, "
        "COUNT(*) AS total FROM appointments",
        (now_local, today_iso),
    ).fetchone()
    return {key: row[key] or 0 for key in ("upcoming", "today", "cancelled", "total")}


def upcoming_booked(conn, now_local):
    return list_appointments(conn, "upcoming", now_local)


# ----- administrators -------------------------------------------------------

# Used so a login attempt for an unknown user costs the same as a real check.
_DUMMY_HASH = generate_password_hash("not-a-real-password")


def admin_count(conn):
    return conn.execute("SELECT COUNT(*) FROM admin_users").fetchone()[0]


def get_admin(conn, admin_id):
    return conn.execute(
        "SELECT id, username FROM admin_users WHERE id = ?", (admin_id,)
    ).fetchone()


def verify_admin(conn, username, password):
    """Return the admin row when the credentials are correct, else None."""
    row = conn.execute(
        "SELECT id, username, password_hash FROM admin_users WHERE username = ?",
        (username,),
    ).fetchone()
    if row is None:
        check_password_hash(_DUMMY_HASH, password)
        return None
    return row if check_password_hash(row["password_hash"], password) else None


def upsert_admin(conn, username, password):
    """Create the admin or reset their password. Returns True when created."""
    password_hash = generate_password_hash(password)
    existing = conn.execute(
        "SELECT id FROM admin_users WHERE username = ?", (username,)
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE admin_users SET password_hash = ? WHERE id = ?",
            (password_hash, existing["id"]),
        )
        return False
    conn.execute(
        "INSERT INTO admin_users (username, password_hash, created_at) VALUES (?, ?, ?)",
        (username, password_hash, utc_now_iso()),
    )
    return True
