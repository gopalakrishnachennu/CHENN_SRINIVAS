from __future__ import annotations

import os

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from resume_engine.ui.auth import require_auth
from resume_engine.ui.csrf import csrf_protect
from resume_engine.ui.services import config_service

bp = Blueprint("settings", __name__, url_prefix="/settings")

def _openai_status():
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if key and "PASTE" not in key.upper() and key != "your_real_key_here":
        return "CONFIGURED"
    return "NOT CONFIGURED"

@bp.route("/", methods=["GET", "POST"])
@require_auth
@csrf_protect
def index():
    if request.method == "POST":
        key = request.form.get("key") or ""
        value = request.form.get("value")
        try:
            config_service.set_setting(key, value, actor=session.get("username"))
            flash("Setting saved", "success")
        except Exception as exc:  # noqa: BLE001
            flash(str(exc), "error")
        return redirect(url_for("settings.index"))
    return render_template(
        "pages/settings.html",
        settings=config_service.list_settings(),
        versions=config_service.get_configuration_versions(limit=50),
        openai_status=_openai_status(),
    )

@bp.post("/rollback")
@require_auth
@csrf_protect
def rollback():
    try:
        config_service.rollback_configuration(int(request.form.get("version_id")), actor=session.get("username"))
        flash("Rolled back", "success")
    except Exception as exc:  # noqa: BLE001
        flash(str(exc), "error")
    return redirect(url_for("settings.index"))
