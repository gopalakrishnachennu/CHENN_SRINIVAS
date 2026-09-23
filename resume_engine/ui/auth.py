"""Operator UI authentication helpers (Gate 4).

When RESUME_ENGINE_UI_PASSWORD is set, all UI routes (except /login, /logout, /healthz)
require an authenticated session.

Username defaults to `operator` (override with RESUME_ENGINE_UI_USER).
When password is unset, auth is disabled for local open use (documented).
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Callable
from functools import wraps

from flask import Flask, redirect, request, session, url_for

from resume_engine.config.settings import load_local_environment


def ui_password() -> str | None:
    load_local_environment()
    value = (os.getenv("RESUME_ENGINE_UI_PASSWORD") or "").strip()
    return value or None


def ui_username() -> str:
    load_local_environment()
    return (os.getenv("RESUME_ENGINE_UI_USER") or "operator").strip() or "operator"


def auth_enabled() -> bool:
    return ui_password() is not None


def configure_app_secret(app: Flask) -> None:
    load_local_environment()
    secret = (os.getenv("RESUME_ENGINE_UI_SECRET") or "").strip()
    if not secret:
        # Ephemeral secret for local/dev — sessions reset on process restart.
        secret = secrets.token_hex(32)
    app.secret_key = secret


def verify_credentials(username: str, password: str) -> bool:
    expected_user = ui_username()
    expected_pass = ui_password()
    if expected_pass is None:
        return True
    # Constant-time compare for password; username equality is fine for operator UI.
    user_ok = secrets.compare_digest(username or "", expected_user)
    pass_ok = secrets.compare_digest(password or "", expected_pass)
    return user_ok and pass_ok


def login_user(username: str) -> None:
    session["authenticated"] = True
    session["username"] = username
    session.permanent = True


def logout_user() -> None:
    session.clear()


def is_authenticated() -> bool:
    if not auth_enabled():
        return True
    return bool(session.get("authenticated"))


def require_auth(view: Callable):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not auth_enabled() or is_authenticated():
            return view(*args, **kwargs)
        return redirect(url_for("login", next=request.path))

    return wrapped


def safe_next_url(value: str | None, *, fallback: str | None = None) -> str:
    """
    Allow only local application-relative redirect targets.

    Rejects absolute URLs, protocol-relative URLs, and javascript/data schemes.
    """
    default = fallback if fallback is not None else url_for("index")
    if value is None:
        return default
    candidate = str(value).strip()
    if not candidate:
        return default
    # Must be a relative path starting with a single slash (not //).
    if not candidate.startswith("/") or candidate.startswith("//"):
        return default
    if "\\" in candidate or "://" in candidate:
        return default
    path_only = candidate.split("?", 1)[0].split("#", 1)[0]
    if path_only.lower().startswith(("/javascript:", "/data:", "/vbscript:")):
        return default
    return candidate
