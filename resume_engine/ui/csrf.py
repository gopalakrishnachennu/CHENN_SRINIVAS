"""CSRF protection for Phase 3.1 operator UI mutations."""

from __future__ import annotations

import secrets
from functools import wraps

from flask import abort, request, session


def ensure_csrf_token() -> str:
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def validate_csrf(token: str | None) -> bool:
    expected = session.get("_csrf_token")
    if not expected or not token:
        return False
    return secrets.compare_digest(str(token), str(expected))


def csrf_protect(view):
    """Require a valid CSRF token for unsafe HTTP methods."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
            if not validate_csrf(token):
                abort(400, description="Invalid or missing CSRF token")
        return view(*args, **kwargs)

    return wrapped
