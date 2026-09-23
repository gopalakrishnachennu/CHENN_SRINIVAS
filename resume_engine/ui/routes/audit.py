from __future__ import annotations

from flask import Blueprint, render_template

from resume_engine.ui.auth import require_auth
from resume_engine.ui.services import audit_service

bp = Blueprint("audit", __name__, url_prefix="/audit")

@bp.get("/")
@require_auth
def index():
    return render_template("pages/audit.html", events=audit_service.list_audit_events(limit=300))
