from __future__ import annotations

import json

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for

from resume_engine.ui.auth import require_auth
from resume_engine.ui.csrf import csrf_protect
from resume_engine.ui.services import generation_service
from resume_engine.ui.services.config_service import get_effective_setting

bp = Blueprint("generation", __name__, url_prefix="/generate")

@bp.route("/", methods=["GET", "POST"])
@require_auth
@csrf_protect
def index():
    if request.method == "POST":
        payload = {
            "blueprint_path": request.form.get("blueprint_path"),
            "generation_mode": request.form.get("generation_mode") or "TEMPLATE",
            "candidate_profile_path": request.form.get("candidate_profile_path") or None,
            "variant_count": int(request.form.get("variant_count") or get_effective_setting("default_variant_count")),
            "model": request.form.get("model") or get_effective_setting("default_openai_model"),
            "run_id": request.form.get("run_id") or None,
            "use_laya": bool(request.form.get("use_laya")),
            "repair": bool(request.form.get("repair")),
            "export_docx": bool(request.form.get("export_docx")),
            "export_pdf": bool(request.form.get("export_pdf")),
        }
        try:
            job = generation_service.create_generation_job(payload, actor=session.get("username"))
            flash("Generation queued", "success")
            return redirect(url_for("generation.live", job_id=job["job_id"]))
        except Exception as exc:  # noqa: BLE001
            flash(str(exc), "error")
    return render_template(
        "pages/generate.html",
        blueprint_path=request.args.get("blueprint"),
        candidate_profile_path="candidate_profile.json",
        defaults={
            "variant_count": get_effective_setting("default_variant_count"),
            "model": get_effective_setting("default_openai_model"),
            "laya": get_effective_setting("laya_default_enabled"),
            "repair": get_effective_setting("repair_default_enabled"),
            "docx": get_effective_setting("default_export_docx"),
            "pdf": get_effective_setting("default_export_pdf"),
        },
        jobs=generation_service.list_jobs(),
    )

@bp.get("/live/<job_id>")
@require_auth
def live(job_id: str):
    job = generation_service.get_job(job_id)
    return render_template("pages/generation_live.html", job=job, job_json=json.dumps(job, indent=2, default=str))

@bp.get("/api/jobs/<job_id>/status")
@require_auth
def job_status(job_id: str):
    return jsonify(generation_service.get_job(job_id))
