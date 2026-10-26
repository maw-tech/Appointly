"""SQLite connection handling, schema initialisation and CLI commands."""
import os
import sqlite3
from contextlib import contextmanager

import click
from flask import current_app, g
from flask.cli import with_appcontext

SCHEMA_FILE = os.path.join(os.path.dirname(__file__), "schema.sql")


def connect(path):
    """Open a connection in autocommit mode; multi-step writes use transaction()."""
    conn = sqlite3.connect(path, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db():
    """Return the connection for the current request, opening it if needed."""
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


@contextmanager
def transaction(conn):
    """Run a block inside BEGIN IMMEDIATE ... COMMIT, rolling back on error.

    BEGIN IMMEDIATE takes the write lock up front, so two simultaneous
    bookings cannot both pass the availability check before inserting.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def init_schema(path):
    """Create tables, indexes and demo availability if they do not exist."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    with open(SCHEMA_FILE, encoding="utf-8") as fh:
        script = fh.read()
    conn = connect(path)
    try:
        conn.executescript(script)
    finally:
        conn.close()


def reset_database(path):
    if os.path.exists(path):
        os.remove(path)
    init_schema(path)


# --------------------------------------------------------------------------
# CLI commands:  flask --app appointly <command>
# --------------------------------------------------------------------------

@click.command("init-db")
@with_appcontext
@click.option("--reset", is_flag=True, help="Delete ALL existing data and start fresh.")
def init_db_command(reset):
    """Create the database tables and default weekly availability."""
    path = current_app.config["DATABASE"]
    if reset:
        click.confirm(f"This permanently deletes all data in {path}. Continue?", abort=True)
        reset_database(path)
    else:
        init_schema(path)
    click.echo(f"Database ready: {path}")


@click.command("create-admin")
@with_appcontext
@click.option("--username", prompt=True, default="admin", show_default=True)
@click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
def create_admin_command(username, password):
    """Create the administrator account (or reset its password)."""
    from . import models

    username = username.strip()
    if not username:
        raise click.BadParameter("Username cannot be empty.", param_hint="--username")
    if len(password) < 8:
        raise click.BadParameter("Password must be at least 8 characters.", param_hint="--password")
    created = models.upsert_admin(get_db(), username, password)
    click.echo(f"Administrator '{username}' {'created' if created else 'password updated'}.")


@click.command("seed-demo")
@with_appcontext
def seed_demo_command():
    """Add a few bookings for FICTIONAL customers to demonstrate the dashboard."""
    from . import booking, scheduling

    customers = [
        ("Jordan Rivera", "jordan.rivera@example.com", "Algebra review before the midterm."),
        ("Priya Natarajan", "priya.n@example.com", "Essay structure feedback."),
        ("Sam Okafor", "sam.okafor@example.com", ""),
        ("Lena Fischer", "lena.fischer@example.org", "First session - placement check."),
    ]
    conn = get_db()
    now = scheduling.current_time()
    days = scheduling.booking_window(now, current_app.config["BOOKING_WINDOW_DAYS"])
    made = 0
    # Start tomorrow so the demo data is clearly upcoming; spread over the window.
    for day in days[1:]:
        if made == len(customers):
            break
        slots = booking.available_slots_for_day(conn, day, now)
        if len(slots) < 3:
            continue
        name, email, notes = customers[made]
        appt = booking.book_appointment(
            conn, name=name, email=email, notes=notes, day=day, start=slots[made % len(slots)], now=now
        )
        click.echo(f"Booked {appt['customer_name']} on {appt['appointment_date']} at {appt['start_time']}")
        made += 1
    click.echo(f"Added {made} demo appointment(s).")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(create_admin_command)
    app.cli.add_command(seed_demo_command)
