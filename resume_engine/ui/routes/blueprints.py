from __future__ import annotations

from flask import Blueprint, Response, flash, redirect, render_template, request, session, url_for

from resume_engine.ui.auth import require_auth
from resume_engine.ui.csrf import csrf_protect
from resume_engine.ui.services import blueprint_service

bp = Blueprint("blueprints", __name__, url_prefix="/blueprints")

def _split(text: str) -> list[str]:
    return [p.strip() for p in (text or "").split(",") if p.strip()]

@bp.get("/")
@require_auth
def index():
    return render_template("pages/blueprints.html", blueprints=blueprint_service.list_blueprints())

@bp.route("/<jd_hash>", methods=["GET", "POST"])
@require_auth
@csrf_protect
def detail(jd_hash: str):
    data = blueprint_service.load_blueprint(jd_hash)
    if request.method == "POST":
        job = dict(data.get("job") or {})
        job["target_title"] = request.form.get("target_title") or job.get("target_title")
        job["seniority"] = request.form.get("seniority") or job.get("seniority")
        job["primary_family"] = request.form.get("primary_family") or job.get("primary_family")
        job["secondary_family"] = request.form.get("secondary_family") or job.get("secondary_family")
        try:
            job["hybrid_probability"] = float(request.form.get("hybrid_probability") or job.get("hybrid_probability") or 0)
        except ValueError:
            flash("Invalid hybrid probability", "error")
            return redirect(url_for("blueprints.detail", jd_hash=jd_hash))
        skills = dict(data.get("priority_skills") or {})
        skills["P1"] = _split(request.form.get("p1", ""))
        skills["P2"] = _split(request.form.get("p2", ""))
        skills["P3"] = _split(request.form.get("p3", ""))
        skills["P4"] = _split(request.form.get("p4", ""))
        contract = dict(data.get("generation_contract") or {})
        contract["allowed_technologies"] = _split(request.form.get("allowed", ""))
        data["job"] = job
        data["priority_skills"] = skills
        data["generation_contract"] = contract
        blueprint_service.save_new_version(
            jd_hash, data, actor=session.get("username"), note=request.form.get("note")
        )
        flash("Saved new blueprint version", "success")
        return redirect(url_for("blueprints.detail", jd_hash=jd_hash))
    return render_template(
        "pages/blueprint_detail.html",
        jd_hash=jd_hash,
        job=data.get("job") or {},
        skills=data.get("priority_skills") or {},
        allowed=(data.get("generation_contract") or {}).get("allowed_technologies") or [],
        versions=blueprint_service.list_versions(jd_hash),
    )

@bp.get("/<jd_hash>/download")
@require_auth
def download(jd_hash: str):
    import json
    data = blueprint_service.load_blueprint(jd_hash)
    return Response(json.dumps(data, indent=2), mimetype="application/json",
                    headers={"Content-Disposition": f"attachment; filename={jd_hash}.json"})
