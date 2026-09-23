from __future__ import annotations

from flask import Blueprint, render_template, request

from resume_engine.ui.auth import require_auth
from resume_engine.ui.services import strategy_service

bp = Blueprint("strategies", __name__, url_prefix="/strategies")

@bp.get("/")
@require_auth
def index():
    blueprint_path = request.args.get("blueprint") or ""
    overview = None
    if blueprint_path:
        try:
            overview = strategy_service.strategy_overview(blueprint_path)
        except Exception as exc:  # noqa: BLE001
            overview = None
            from flask import flash
            flash(str(exc), "error")
    return render_template("pages/strategies.html", blueprint_path=blueprint_path, overview=overview)
