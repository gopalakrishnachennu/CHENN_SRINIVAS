from __future__ import annotations

from flask import Blueprint, render_template

from resume_engine.ui.auth import require_auth
from resume_engine.ui.services.dashboard_service import dashboard_metrics

bp = Blueprint("dashboard", __name__)

@bp.get("/")
@require_auth
def index():
    return render_template("pages/dashboard.html", metrics=dashboard_metrics())
