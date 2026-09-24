from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from resume_engine.ui.auth import require_auth
from resume_engine.ui.csrf import csrf_protect
from resume_engine.ui.services import candidate_service
from resume_engine.ui.services.family_registry_service import family_options

bp = Blueprint("candidates", __name__, url_prefix="/candidates")


def _actor():
    return session.get("username")


def _parse_companies():
    companies = []
    names = request.form.getlist("company_name")
    starts = request.form.getlist("company_start")
    ends = request.form.getlist("company_end")
    for i, name in enumerate(names):
        name = (name or "").strip()
        if not name:
            continue
        companies.append({
            "company": name,
            "start_date": (starts[i] if i < len(starts) else "") or "",
            "end_date": (ends[i] if i < len(ends) else "") or "",
        })
    return companies


def _parse_payload():
    certs = request.form.get("certifications") or ""
    education_raw = (request.form.get("education") or "").strip()
    education = []
    if education_raw:
        education = [{"description": line.strip()} for line in education_raw.splitlines() if line.strip()]
    return {
        "candidate_name": request.form.get("candidate_name") or "",
        "email": request.form.get("email") or "",
        "phone": request.form.get("phone") or "",
        "location": request.form.get("location") or "",
        "linkedin": request.form.get("linkedin") or "",
        "primary_family": request.form.get("primary_family") or "",
        "secondary_family": request.form.get("secondary_family") or None,
        "companies": _parse_companies(),
        "education": education,
        "certifications": [c.strip() for c in certs.split(",") if c.strip()],
    }


@bp.get("/")
@require_auth
def index():
    from resume_engine.ui.services import create_resume_service, job_service, match_service

    profiles = candidate_service.list_profiles()
    jobs = job_service.list_jobs_lite(limit=5000)
    cards = []
    for p in profiles:
        summary = match_service.match_summary_for_candidate(p, jobs)
        resumes = [r for r in create_resume_service.list_resume_library(200) if r.get("candidate_id") == p["id"]]
        cards.append({
            **p,
            "match_count": summary["matched_jobs"],
            "match_summary": summary,
            "resume_count": len(resumes),
        })
    return render_template("pages/candidates.html", cards=cards)


@bp.route("/new", methods=["GET", "POST"])
@require_auth
@csrf_protect
def create():
    if request.method == "POST":
        try:
            profile = candidate_service.create_profile(_parse_payload(), actor=_actor())
            flash("Candidate created", "success")
            return redirect(url_for("candidates.view", profile_id=profile["id"]))
        except Exception as exc:  # noqa: BLE001
            flash(str(exc), "error")
    return render_template("pages/candidate_edit.html", profile=None, family_options=family_options())


@bp.get("/<profile_id>")
@require_auth
def view(profile_id: str):
    profile = candidate_service.get_profile(profile_id)
    from resume_engine.ui.services import job_service, match_service

    summary = match_service.match_summary_for_candidate(
        profile, job_service.list_jobs_lite(limit=5000)
    )
    return render_template(
        "pages/candidate_view.html",
        profile=profile,
        match_count=summary["matched_jobs"],
        match_summary=summary,
    )


@bp.route("/<profile_id>/edit", methods=["GET", "POST"])
@require_auth
@csrf_protect
def edit(profile_id: str):
    profile = candidate_service.get_profile(profile_id)
    if request.method == "POST":
        try:
            profile = candidate_service.update_profile(profile_id, _parse_payload(), actor=_actor())
            flash("Candidate updated", "success")
            return redirect(url_for("candidates.view", profile_id=profile_id))
        except Exception as exc:  # noqa: BLE001
            flash(str(exc), "error")
    return render_template("pages/candidate_edit.html", profile=profile, family_options=family_options())


@bp.post("/<profile_id>/duplicate")
@require_auth
@csrf_protect
def duplicate(profile_id: str):
    profile = candidate_service.duplicate_profile(profile_id, actor=_actor())
    flash("Duplicated", "success")
    return redirect(url_for("candidates.view", profile_id=profile["id"]))


@bp.post("/<profile_id>/archive")
@require_auth
@csrf_protect
def archive(profile_id: str):
    candidate_service.archive_profile(profile_id, actor=_actor())
    flash("Archived", "success")
    return redirect(url_for("candidates.index"))
