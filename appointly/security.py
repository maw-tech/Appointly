"""CSRF protection, admin login guard and HTTP security headers."""
import functools
import hmac
import secrets

from flask import abort, current_app, flash, g, redirect, request, session, url_for

from . import models
from .db import get_db


def csrf_token():
    """Per-session token embedded in every form as a hidden field."""
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(32)
    return session["_csrf_token"]


def csrf_protect():
    """Reject state-changing requests that do not carry the session's token."""
    if request.method != "POST" or not current_app.config.get("CSRF_ENABLED", True):
        return
    expected = session.get("_csrf_token")
    submitted = request.form.get("csrf_token", "")
    if not expected or not hmac.compare_digest(expected, submitted):
        abort(400, description="Your form session expired. Please reload the page and try again.")


def load_admin():
    """Expose the logged-in administrator (or None) as g.admin."""
    admin_id = session.get("admin_id")
    g.admin = models.get_admin(get_db(), admin_id) if admin_id else None


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if g.get("admin") is None:
            flash("Please log in to access the admin area.", "warning")
            target = request.full_path if request.query_string else request.path
            return redirect(url_for("admin.login", next=target))
        return view(*args, **kwargs)

    return wrapped


def is_safe_next(target):
    """Only allow redirects to local paths (prevents open redirects)."""
    return bool(target) and target.startswith("/") and not target.startswith("//") and "\\" not in target


def set_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    if request.path.startswith("/admin"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


def init_app(app):
    app.before_request(csrf_protect)
    app.before_request(load_admin)
    app.after_request(set_security_headers)
    app.jinja_env.globals["csrf_token"] = csrf_token
