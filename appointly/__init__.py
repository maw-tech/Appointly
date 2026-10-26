"""Appointly - appointment scheduling for a single service provider."""
import os
import secrets
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Flask, render_template
from flask_bootstrap import Bootstrap5

from . import db, scheduling, security
from .config import Config


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    if not app.config.get("SECRET_KEY"):
        # Sessions still work, but are invalidated every time the server restarts.
        app.config["SECRET_KEY"] = secrets.token_hex(32)
        app.logger.warning("SECRET_KEY is not set; using a temporary key. Copy .env.example to .env.")

    if not app.config.get("DATABASE"):
        app.config["DATABASE"] = os.path.join(app.instance_path, "appointly.sqlite3")

    try:
        ZoneInfo(app.config["TIMEZONE"])
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise RuntimeError(f"Invalid APPOINTLY_TIMEZONE: {app.config['TIMEZONE']!r}") from exc

    Bootstrap5(app)
    db.init_app(app)
    security.init_app(app)
    # Idempotent: creates tables and demo availability only if missing.
    db.init_schema(app.config["DATABASE"])

    from .admin import bp as admin_bp
    from .public import bp as public_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp)

    register_template_helpers(app)
    register_error_handlers(app)
    return app


def register_template_helpers(app):
    @app.context_processor
    def inject_globals():
        return {
            "provider_name": app.config["PROVIDER_NAME"],
            "timezone_name": app.config["TIMEZONE"],
            "slot_minutes": scheduling.SLOT_MINUTES,
        }

    @app.template_filter("long_date")
    def long_date(value):
        day = scheduling.parse_date(value) if isinstance(value, str) else value
        return day.strftime("%A, %B ") + str(day.day) + day.strftime(", %Y") if day else value

    @app.template_filter("short_date")
    def short_date(value):
        day = scheduling.parse_date(value) if isinstance(value, str) else value
        return day.strftime("%a %b ") + str(day.day) if day else value

    @app.template_filter("ampm")
    def ampm(hhmm):
        t = scheduling.parse_time(hhmm)
        if t is None:
            return hhmm
        hour = t.hour % 12 or 12
        return f"{hour}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"

    app.jinja_env.globals["end_time_of"] = scheduling.end_time_of


def register_error_handlers(app):
    def render_error(code, title, message):
        return render_template("error.html", code=code, title=title, message=message), code

    @app.errorhandler(400)
    def bad_request(err):
        return render_error(400, "Bad request", err.description or "The request could not be processed.")

    @app.errorhandler(404)
    def not_found(_err):
        return render_error(404, "Page not found", "The page you were looking for does not exist.")

    @app.errorhandler(405)
    def method_not_allowed(_err):
        return render_error(405, "Not allowed", "That action is not allowed on this page.")

    @app.errorhandler(500)
    def server_error(_err):
        return render_error(500, "Something went wrong", "An unexpected error occurred. Please try again.")
