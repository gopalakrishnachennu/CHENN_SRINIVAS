from __future__ import annotations

from flask import Blueprint, render_template

from resume_engine.ui.auth import require_auth
from resume_engine.ui.services import system_service

bp = Blueprint("system", __name__, url_prefix="/system")

@bp.get("/")
@require_auth
def index():
    return render_template("pages/system.html", info=system_service.system_info())
