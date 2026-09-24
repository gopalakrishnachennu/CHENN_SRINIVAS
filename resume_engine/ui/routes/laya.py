from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from resume_engine.ui.auth import require_auth
from resume_engine.ui.csrf import csrf_protect
from resume_engine.ui.services import laya_service

bp = Blueprint("laya", __name__, url_prefix="/advanced/laya")


@bp.get("/")
@require_auth
def index():
    return render_template("pages/laya.html", data=laya_service.laya_status())


@bp.post("/toggle")
@require_auth
@csrf_protect
def toggle():
    enabled = request.form.get("enabled") == "on"
    laya_service.set_laya_enabled(enabled, actor=session.get("username"))
    flash(f"Laya semantic validation {'ON' if enabled else 'OFF'}", "success")
    return redirect(url_for("laya.index"))
