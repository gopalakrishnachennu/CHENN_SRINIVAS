from __future__ import annotations

from flask import Blueprint, render_template

from resume_engine.ui.auth import require_auth
from resume_engine.ui.services import dashboard_service

bp = Blueprint("dashboard", __name__)


@bp.get("/")
@require_auth
def index():
    data = dashboard_service.dashboard_payload()
    return render_template("pages/dashboard.html", data=data)
