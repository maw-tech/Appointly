"""Administrator pages: login, reservations dashboard and weekly availability."""
from flask import (Blueprint, abort, flash, g, redirect, render_template, request,
                   session, url_for)

from . import booking, models, scheduling
from .db import get_db
from .security import is_safe_next, login_required

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/login", methods=["GET", "POST"])
def login():
    conn = get_db()
    if g.admin:
        return redirect(url_for("admin.dashboard"))

    error = None
    username = ""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        admin = models.verify_admin(conn, username, password) if username and password else None
        if admin is None:
            error = "Incorrect username or password."
        else:
            session.clear()  # fresh session on login (prevents session fixation)
            session.permanent = True
            session["admin_id"] = admin["id"]
            flash(f"Welcome back, {admin['username']}.", "success")
            target = request.args.get("next", "")
            return redirect(target if is_safe_next(target) else url_for("admin.dashboard"))

    return render_template(
        "admin/login.html",
        error=error,
        username=username,
        no_admin=models.admin_count(conn) == 0,
    ), (401 if error else 200)


@bp.post("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("public.index"))


@bp.get("/")
@login_required
def dashboard():
    conn = get_db()
    now = scheduling.current_time()
    now_local = now.strftime("%Y-%m-%d %H:%M")
    view = request.args.get("view", "upcoming")
    if view not in models.VIEWS:
        view = "upcoming"
    search = request.args.get("q", "").strip()[:100]

    return render_template(
        "admin/dashboard.html",
        appointments=models.list_appointments(conn, view, now_local, search),
        counts=models.dashboard_counts(conn, now_local, now.date().isoformat()),
        view=view,
        views=models.VIEWS,
        search=search,
        now_local=now_local,
        outside_hours={a["id"] for a in booking.appointments_outside_hours(conn, now)},
    )


@bp.post("/appointments/<int:appointment_id>/cancel")
@login_required
def cancel(appointment_id):
    conn = get_db()
    appt = models.get_appointment(conn, appointment_id)
    if appt is None:
        abort(404)
    if models.cancel_appointment(conn, appointment_id):
        flash(
            f"Cancelled {appt['customer_name']}'s appointment on "
            f"{appt['appointment_date']} at {appt['start_time']}. The slot is available again.",
            "success",
        )
    else:
        flash("That appointment was already cancelled.", "warning")
    view = request.form.get("view", "upcoming")
    return redirect(url_for("admin.dashboard", view=view if view in models.VIEWS else "upcoming"))


def _parse_availability_form(form):
    """Return (days, errors) for the weekly availability form."""
    options = set(scheduling.time_options())
    days, errors = [], {}
    for weekday, name in enumerate(scheduling.WEEKDAY_NAMES):
        working = form.get(f"working_{weekday}") == "on"
        start = form.get(f"start_{weekday}", "")
        end = form.get(f"end_{weekday}", "")
        if start not in options or end not in options:
            errors[weekday] = f"{name}: choose start and end times from the list."
            start, end = start if start in options else "09:00", end if end in options else "17:00"
        elif start >= end:
            # The database CHECK requires start < end even for days off.
            errors[weekday] = f"{name}: the end time must be later than the start time."
        days.append({"weekday": weekday, "is_working": int(working), "start_time": start, "end_time": end})
    return days, errors


@bp.route("/availability", methods=["GET", "POST"])
@login_required
def availability():
    conn = get_db()
    if request.method == "POST":
        days, errors = _parse_availability_form(request.form)
        if errors:
            flash("Availability was not saved. Please fix the highlighted days.", "danger")
            return render_template(
                "admin/availability.html", days=days, errors=errors,
                options=scheduling.time_options(), weekday_names=scheduling.WEEKDAY_NAMES,
            ), 400
        models.save_weekly_availability(conn, days)
        flash("Weekly availability saved.", "success")
        conflicts = booking.appointments_outside_hours(conn, scheduling.current_time())
        if conflicts:
            flash(
                f"{len(conflicts)} upcoming appointment(s) now fall outside your working hours. "
                "They are still booked — review them on the dashboard and cancel if needed.",
                "warning",
            )
        return redirect(url_for("admin.availability"))

    days = [dict(row) for row in models.get_weekly_availability(conn)]
    return render_template(
        "admin/availability.html", days=days, errors={},
        options=scheduling.time_options(), weekday_names=scheduling.WEEKDAY_NAMES,
    )
