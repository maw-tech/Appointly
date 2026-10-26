"""Customer-facing pages: home, slot picker, booking form and confirmation."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from . import booking, models, scheduling, validation
from .db import get_db

bp = Blueprint("public", __name__)


@bp.get("/")
def index():
    weekly = models.get_weekly_availability(get_db())
    return render_template("index.html", weekly=weekly, weekday_names=scheduling.WEEKDAY_NAMES)


@bp.get("/book")
def choose_slot():
    conn = get_db()
    now = scheduling.current_time()
    overview = booking.availability_overview(conn, now)

    selected = scheduling.parse_date(request.args.get("date", ""))
    days = [day for day, _ in overview]
    if selected not in days:
        # Default to the first day that still has an open slot.
        selected = next((day for day, slots in overview if slots), days[0])
    slots = dict(overview)[selected]

    return render_template(
        "book.html",
        overview=overview,
        selected=selected,
        slots=slots,
        any_open=any(s for _, s in overview),
    )


def _requested_slot(source):
    day = scheduling.parse_date(source.get("date", ""))
    start = source.get("time", "")
    return day, (start if scheduling.parse_time(start) else None)


@bp.get("/book/details")
def booking_form():
    day, start = _requested_slot(request.args)
    try:
        booking.check_slot(get_db(), day, start, scheduling.current_time())
    except booking.SlotUnavailableError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("public.choose_slot", date=day.isoformat() if day else None))
    return render_template("book_details.html", day=day, start=start, values={}, errors={})


@bp.post("/book")
def create_booking():
    conn = get_db()
    day, start = _requested_slot(request.form)
    values, errors = validation.validate_customer(request.form)

    if errors:
        if day is None or start is None:
            flash("Please choose a valid date and time from the list.", "danger")
            return redirect(url_for("public.choose_slot"))
        flash("Please correct the highlighted fields.", "danger")
        return render_template(
            "book_details.html", day=day, start=start, values=values, errors=errors
        ), 400

    try:
        appt = booking.book_appointment(
            conn, name=values["name"], email=values["email"], notes=values["notes"],
            day=day, start=start, now=scheduling.current_time(),
        )
    except booking.SlotUnavailableError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("public.choose_slot", date=day.isoformat() if day else None))

    flash("Your appointment is confirmed.", "success")
    return redirect(url_for("public.confirmation", reference=appt["reference"]))


@bp.get("/booking/<reference>")
def confirmation(reference):
    appt = models.get_appointment_by_reference(get_db(), reference)
    if appt is None:
        abort(404)
    return render_template("confirmation.html", appt=appt)
