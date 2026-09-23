from __future__ import annotations

import json

from flask import Blueprint, abort, flash, redirect, render_template, session, url_for

from resume_engine.ui.auth import require_auth
from resume_engine.ui.csrf import csrf_protect
from resume_engine.ui.services import learning_service

bp = Blueprint("learning", __name__, url_prefix="/learning")

@bp.get("/")
@require_auth
def index():
    data = learning_service.learning_dashboard()
    return render_template(
        "pages/learning.html",
        data=data,
        observations=learning_service.list_observations(limit=100),
    )

@bp.post("/refresh")
@require_auth
@csrf_protect
def refresh():
    learning_service.refresh_evaluation(actor=session.get("username"))
    flash("Evaluation refreshed", "success")
    return redirect(url_for("learning.index"))

@bp.post("/write-report")
@require_auth
@csrf_protect
def write_report():
    path = learning_service.write_report(actor=session.get("username"))
    flash(f"Report written: {path}", "success")
    return redirect(url_for("learning.index"))

@bp.post("/replay-dry")
@require_auth
@csrf_protect
def replay_dry():
    report = learning_service.replay_dry(actor=session.get("username"))
    flash(f"Dry replay complete: usable={report.get('usable_records')}", "success")
    return redirect(url_for("learning.index"))

@bp.post("/replay-train")
@require_auth
@csrf_protect
def replay_train():
    from flask import request
    try:
        learning_service.replay_train(actor=session.get("username"), confirmed=request.form.get("confirm") == "1")
        flash("Historical train completed", "success")
    except Exception as exc:  # noqa: BLE001
        flash(str(exc), "error")
    return redirect(url_for("learning.index"))

@bp.get("/decisions/<int:decision_id>")
@require_auth
def decision(decision_id: int):
    row = learning_service.get_decision(decision_id)
    if row is None:
        abort(404)
    return render_template("pages/learning_decision.html", decision=row, decision_json=json.dumps(row, indent=2, default=str))

@bp.post("/enable-active")
@require_auth
@csrf_protect
def enable_active():
    try:
        learning_service.try_enable_active_mode()
    except Exception as exc:  # noqa: BLE001
        flash(str(exc), "error")
    return redirect(url_for("learning.index"))
