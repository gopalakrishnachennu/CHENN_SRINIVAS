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
from resume_engine.ui.services.blueprint_lifecycle import (
    ANALYSIS_READY,
    ensure_job_blueprint,
)
from resume_engine.ui.services.create_resume_service import PreflightError

bp = Blueprint("create_resume", __name__, url_prefix="/create")


def _matched_for(candidate_id: str | None):
    candidates = candidate_service.list_profiles()
    selected = None
    matched = []
    ready_count = 0
    if candidate_id:
        try:
            selected = candidate_service.get_profile(candidate_id)
            jobs = job_service.list_jobs(limit=2000)
            matched = match_service.list_matches_for_candidate(selected, jobs)
            ready_count = sum(
                1 for m in matched if (m.get("analysis_status") or "").upper() == ANALYSIS_READY
            )
        except KeyError:
            selected = None
    return candidates, selected, matched, ready_count


@bp.route("/", methods=["GET", "POST"])
@require_auth
@csrf_protect
def index():
    candidates = candidate_service.list_profiles()
    candidate_id = request.values.get("candidate") or request.form.get("candidate_id")
    if not candidate_id and candidates:
        candidate_id = candidates[0]["id"]

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
        except PreflightError as exc:
            flash(f"{exc.code}: {exc.message}", "error")
            # Never surface raw blueprint_path errors
            msg = str(exc.message or "")
            if "blueprint_path" in msg.lower():
                flash("Preparing job analysis...", "error")
        except Exception as exc:  # noqa: BLE001
            text = str(exc)
            if "blueprint_path" in text.lower():
                flash("Preparing job analysis failed. Use Analyze Now / Retry Analysis.", "error")
            else:
                flash(text, "error")

    candidates, selected, matched, ready_count = _matched_for(candidate_id)
    preselect_jd = request.args.get("jd") or request.form.get("jd_id")
    first_ready_id = next(
        (m["id"] for m in matched if (m.get("analysis_status") or "").upper() == ANALYSIS_READY),
        None,
    )
    return render_template(
        "pages/create.html",
        candidates=candidates,
        selected=selected,
        matched=matched,
        ready_count=ready_count,
        preselect_jd=preselect_jd,
        first_ready_id=first_ready_id,
    )


@bp.route("/prepare", methods=["POST"])
@require_auth
@csrf_protect
def prepare():
    """Analyze / ensure blueprint for a job without starting generation."""
    candidate_id = request.form.get("candidate_id") or ""
    job_id = request.form.get("jd_id_prepare") or request.form.get("jd_id") or ""
    if not job_id:
        flash("Select a job to analyze", "error")
        return redirect(url_for("create_resume.index", candidate=candidate_id))
    flash("Preparing job analysis...", "info")
    result = ensure_job_blueprint(job_id, actor=session.get("username"))
    if result.get("ok"):
        flash("✓ Job ready", "success")
    else:
        flash(
            f"Job analysis failed: {result.get('error') or result.get('reason') or 'unknown'}",
            "error",
        )
    return redirect(url_for("create_resume.index", candidate=candidate_id, jd=job_id))


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


@bp.get("/jobs/<candidate_id>")
@require_auth
def select_job(candidate_id: str):
    return redirect(url_for("create_resume.index", candidate=candidate_id))


@bp.route("/options/<candidate_id>/<job_id>", methods=["GET", "POST"])
@require_auth
@csrf_protect
def options(candidate_id: str, job_id: str):
    return redirect(url_for("create_resume.index", candidate=candidate_id, jd=job_id))
