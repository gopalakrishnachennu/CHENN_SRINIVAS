from __future__ import annotations

from flask import Blueprint, render_template

from resume_engine.ui.auth import require_auth
from resume_engine.ui.services import repair_service

bp = Blueprint("repairs", __name__, url_prefix="/repairs")

@bp.get("/")
@require_auth
def index():
    return render_template("pages/repairs.html", repairs=repair_service.list_repair_events())
