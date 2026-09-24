"""Create Resume — central product wizard at /create."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from resume_engine.ui.auth import require_auth
from resume_engine.ui.csrf import csrf_protect
from resume_engine.ui.services import (
    candidate_service,
    create_resume_service,
    job_service,
    match_service,
)

bp = Blueprint("create_resume", __name__, url_prefix="/create")


@bp.route("/", methods=["GET", "POST"])
@require_auth
@csrf_protect
def index():
    candidates = candidate_service.list_profiles()
    candidate_id = request.values.get("candidate") or (candidates[0]["id"] if candidates else None)
    selected = None
    matched = []
    if candidate_id:
        try:
            selected = candidate_service.get_profile(candidate_id)
            jobs = job_service.list_jobs(limit=2000)
            matched = match_service.matches_for_candidate(
                selected, jobs,
            )
        except KeyError:
            selected = None

    if request.method == "POST" and request.form.get("action") == "generate":
        try:
            job = create_resume_service.start_create_resume(
                candidate_id=request.form.get("candidate_id") or "",
                jd_id=request.form.get("jd_id") or "",
                variants=int(request.form.get("variants") or 3),
                repair=request.form.get("repair") == "on",
                laya=request.form.get("laya") == "on",
                export_docx=request.form.get("docx") == "on",
                export_pdf=request.form.get("pdf") == "on",
                actor=session.get("username"),
            )
            return redirect(url_for("create_resume.progress", job_id=job["job_id"]))
        except Exception as exc:  # noqa: BLE001
            flash(str(exc), "error")

    preselect_jd = request.args.get("jd")
    return render_template(
        "pages/create.html",
        candidates=candidates,
        selected=selected,
        matched=matched,
        preselect_jd=preselect_jd,
    )


@bp.get("/progress/<job_id>")
@require_auth
def progress(job_id: str):
    from resume_engine.ui.services.generation_service import get_job

    job = get_job(job_id)
    progress_data = create_resume_service.friendly_progress(job)
    return render_template("pages/create_progress.html", job=job, progress=progress_data)


@bp.get("/api/progress/<job_id>")
@require_auth
def api_progress(job_id: str):
    from resume_engine.ui.services.generation_service import get_job

    job = get_job(job_id)
    return create_resume_service.friendly_progress(job)


# Optional multi-step aliases used by older templates
@bp.get("/jobs/<candidate_id>")
@require_auth
def select_job(candidate_id: str):
    return redirect(url_for("create_resume.index", candidate=candidate_id))


@bp.route("/options/<candidate_id>/<job_id>", methods=["GET", "POST"])
@require_auth
@csrf_protect
def options(candidate_id: str, job_id: str):
    return redirect(url_for("create_resume.index", candidate=candidate_id, jd=job_id))
