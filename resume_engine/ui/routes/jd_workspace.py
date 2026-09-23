from __future__ import annotations

import json

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from resume_engine.ui.auth import require_auth
from resume_engine.ui.csrf import csrf_protect
from resume_engine.ui.services import jd_service

bp = Blueprint("jd_workspace", __name__, url_prefix="/jd")

def _actor():
    return session.get("username") or "operator"

@bp.route("/", methods=["GET", "POST"])
@require_auth
@csrf_protect
def index():
    jd_text = ""
    blueprint = None
    blueprint_path = None
    if request.method == "POST":
        action = request.form.get("action") or "analyze"
        if action == "clear":
            return redirect(url_for("jd_workspace.index"))
        if action == "load_example":
            jd_text = jd_service.example_jd()
        else:
            jd_text = request.form.get("jd_text") or ""
            upload = request.files.get("jd_file")
            if upload and upload.filename:
                jd_text = jd_service.extract_text_from_upload(upload.filename, upload.read())
            if action == "save_draft":
                jd_service.save_draft(jd_text, actor=_actor())
                flash("Draft saved", "success")
            elif action == "analyze":
                if not jd_text.strip():
                    flash("JD text required", "error")
                else:
                    try:
                        result = jd_service.analyze_jd(jd_text, actor=_actor())
                        blueprint = result["blueprint"]
                        blueprint_path = result["path"]
                        flash("Phase 1 complete", "success")
                    except Exception as exc:  # noqa: BLE001
                        flash(f"JD analysis failed: {exc}", "error")
    return render_template(
        "pages/jd_workspace.html",
        jd_text=jd_text,
        blueprint=blueprint,
        blueprint_path=blueprint_path,
        blueprint_json=json.dumps(blueprint, indent=2) if blueprint else "",
        drafts=jd_service.list_drafts(),
    )
