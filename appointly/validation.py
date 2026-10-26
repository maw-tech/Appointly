"""Server-side validation of customer-supplied booking fields."""
import re

NAME_MAX = 80
EMAIL_MAX = 254
NOTES_MAX = 500

# Letters (any language), spaces, apostrophes, hyphens and periods.
_NAME_ALLOWED = re.compile(r"^[^\W\d_]+(?:[ '.\-]+[^\W\d_]+)*\.?$")
_EMAIL = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$")
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def clean_name(raw):
    """Return (value, error)."""
    value = " ".join((raw or "").split())  # trim and collapse whitespace
    if not value:
        return value, "Please enter your name."
    if len(value) < 2 or len(value) > NAME_MAX:
        return value, f"Name must be between 2 and {NAME_MAX} characters."
    if not _NAME_ALLOWED.match(value):
        return value, "Name may only contain letters, spaces, apostrophes, hyphens and periods."
    return value, None


def clean_email(raw):
    value = (raw or "").strip().lower()
    if not value:
        return value, "Please enter your email address."
    if len(value) > EMAIL_MAX or ".." in value or not _EMAIL.match(value):
        return value, "Please enter a valid email address, for example name@example.com."
    return value, None


def clean_notes(raw):
    value = _CONTROL_CHARS.sub("", (raw or "").replace("\r\n", "\n")).strip()
    if len(value) > NOTES_MAX:
        return value, f"Notes must be {NOTES_MAX} characters or fewer."
    return value, None


def validate_customer(form):
    """Validate the customer fields of a booking form.

    Returns (cleaned_values, errors) where errors maps field name -> message.
    """
    values, errors = {}, {}
    for field, cleaner in (("name", clean_name), ("email", clean_email), ("notes", clean_notes)):
        value, error = cleaner(form.get(field))
        values[field] = value
        if error:
            errors[field] = error
    return values, errors
