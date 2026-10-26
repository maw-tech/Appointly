"""Application configuration loaded from environment variables (.env)."""
import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


def _int_env(name, default, minimum, maximum):
    """Read an integer environment variable and clamp it to a sensible range."""
    try:
        value = int(os.environ.get(name, default))
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


def _bool_env(name, default=False):
    return os.environ.get(name, str(int(default))).strip().lower() in {"1", "true", "yes", "on"}


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    # None means "use instance/appointly.sqlite3"; resolved in create_app().
    DATABASE = os.environ.get("APPOINTLY_DATABASE") or None
    TIMEZONE = os.environ.get("APPOINTLY_TIMEZONE", "America/New_York")
    PROVIDER_NAME = os.environ.get("APPOINTLY_PROVIDER_NAME", "Riverside Tutoring")
    BOOKING_WINDOW_DAYS = _int_env("APPOINTLY_BOOKING_WINDOW_DAYS", 14, 1, 90)

    # Session cookie hardening
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool_env("SESSION_COOKIE_SECURE")
    PERMANENT_SESSION_LIFETIME = timedelta(hours=2)

    CSRF_ENABLED = True

    # Serve Bootstrap from the installed package so the app works offline.
    BOOTSTRAP_SERVE_LOCAL = True
