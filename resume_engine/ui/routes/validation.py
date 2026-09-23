from __future__ import annotations

import json

from flask import Blueprint, abort, render_template, request

from resume_engine.ui.auth import require_auth
from resume_engine.ui.services import validation_service

bp = Blueprint("validation", __name__, url_prefix="/validation")

@bp.get("/")
@require_auth
def index():
    return render_template("pages/validation.html", reports=validation_service.list_validation_reports())

@bp.get("/detail")
@require_auth
def detail():
    path = request.args.get("path") or ""
    try:
        report = validation_service.load_validation_report(path)
    except (OSError, ValueError, json.JSONDecodeError, KeyError):
        abort(404)
    rows = validation_service.summarize_validators(report)
    return render_template(
        "pages/validation_detail.html",
        report=report,
        rows=rows,
        report_json=json.dumps(report, indent=2, default=str),
    )
