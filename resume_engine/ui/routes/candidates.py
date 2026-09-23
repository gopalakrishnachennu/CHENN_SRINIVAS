from __future__ import annotations

import json

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from resume_engine.ui.auth import require_auth
from resume_engine.ui.csrf import csrf_protect
from resume_engine.ui.services import candidate_service

bp = Blueprint("candidates", __name__, url_prefix="/candidates")

def _actor():
    return session.get("username")

def _parse_payload():
    def split(v):
        return [p.strip() for p in (v or "").split(",") if p.strip()]
    def jload(v, default):
        try:
            return json.loads(v) if v and v.strip() else default
        except json.JSONDecodeError as exc:
            raise ValueError(str(exc)) from exc
    return {
        "candidate_name": request.form.get("candidate_name") or "",
        "email": request.form.get("email") or "",
        "phone": request.form.get("phone") or "",
        "location": request.form.get("location") or "",
        "linkedin": request.form.get("linkedin") or "",
        "website": request.form.get("website") or "",
        "target_background_summary": request.form.get("target_background_summary") or "",
        "technical_skills": split(request.form.get("technical_skills")),
        "experience": jload(request.form.get("experience_json"), []),
        "projects": jload(request.form.get("projects_json"), []),
        "education": jload(request.form.get("education_json"), []),
        "certifications": split(request.form.get("certifications")),
    }

@bp.get("/")
@require_auth
def index():
    return render_template("pages/candidates.html", profiles=candidate_service.list_profiles())

@bp.route("/new", methods=["GET", "POST"])
@require_auth
@csrf_protect
def create():
    if request.method == "POST":
        try:
            profile = candidate_service.create_profile(_parse_payload(), actor=_actor())
            flash("Candidate created", "success")
            return redirect(url_for("candidates.edit", profile_id=profile["id"]))
        except Exception as exc:  # noqa: BLE001
            flash(str(exc), "error")
    return render_template(
        "pages/candidate_edit.html",
        profile=None,
        experience_json="[]",
        projects_json="[]",
        education_json="[]",
    )

@bp.route("/<profile_id>", methods=["GET", "POST"])
@require_auth
@csrf_protect
def edit(profile_id: str):
    profile = candidate_service.get_profile(profile_id)
    if request.method == "POST":
        try:
            profile = candidate_service.update_profile(profile_id, _parse_payload(), actor=_actor())
            flash("Candidate updated (new version)", "success")
        except Exception as exc:  # noqa: BLE001
            flash(str(exc), "error")
    p = profile["payload"]
    return render_template(
        "pages/candidate_edit.html",
        profile=profile,
        experience_json=json.dumps(p.get("experience") or [], indent=2),
        projects_json=json.dumps(p.get("projects") or [], indent=2),
        education_json=json.dumps(p.get("education") or [], indent=2),
    )

@bp.post("/<profile_id>/duplicate")
@require_auth
@csrf_protect
def duplicate(profile_id: str):
    profile = candidate_service.duplicate_profile(profile_id, actor=_actor())
    flash("Duplicated", "success")
    return redirect(url_for("candidates.edit", profile_id=profile["id"]))

@bp.post("/<profile_id>/archive")
@require_auth
@csrf_protect
def archive(profile_id: str):
    candidate_service.archive_profile(profile_id, actor=_actor())
    flash("Archived", "success")
    return redirect(url_for("candidates.index"))
