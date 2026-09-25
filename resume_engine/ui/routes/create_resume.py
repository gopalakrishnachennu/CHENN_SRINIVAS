"""Create Resume — central product wizard at /create."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from resume_engine.ui.auth import require_auth
from resume_engine.ui.csrf import csrf_protect
from resume_engine.ui.services import (
    candidate_service,
    config_service,
    create_resume_service,
    job_service,
    match_service,
)
from resume_engine.ui.services import openai_command_service
from resume_engine.ui.services import project_source_service
from resume_engine.ui.services.family_registry_service import family_options
from resume_engine.ui.services.blueprint_lifecycle import ensure_job_blueprint
from resume_engine.ui.services.create_resume_service import PreflightError

bp = Blueprint("create_resume", __name__, url_prefix="/create")


@bp.route("/project-sources", methods=["GET", "POST"])
@require_auth
@csrf_protect
def project_sources():
    if request.method == "POST":
        try:
            action = request.form.get("action")
            if action == "import_candidate":
                profile = project_source_service.import_candidate(
                    primary_family=request.form.get("primary_family") or "",
                    secondary_family=request.form.get("secondary_family") or None,
                    actor=session.get("username"),
                )
                flash("Verified project profile imported. Review the fact card before generation.", "success")
                return redirect(url_for("candidates.view", profile_id=profile["id"]))
            if action == "refresh_candidate":
                if request.form.get("confirm_refresh") != "on":
                    raise ValueError("Confirm that project-file facts should replace this candidate's current facts.")
                profile = project_source_service.refresh_candidate(actor=session.get("username"))
                flash("Candidate refreshed from the project file. Review the updated facts.", "success")
                return redirect(url_for("candidates.view", profile_id=profile["id"]))
            if action == "create_draft":
                source = project_source_service.jd_source()
                if source is None:
                    raise ValueError("real_jd.txt is not available in this project.")
                job = create_resume_service.start_project_jd_draft(
                    candidate_id=request.form.get("candidate_id") or "",
                    jd_text=source["jd_text"],
                    target_title=source["title"],
                    actor=session.get("username"),
                )
                return redirect(url_for("create_resume.progress", job_id=job["job_id"]))
            raise ValueError("Choose an import or draft action.")
        except (ValueError, KeyError, PreflightError) as exc:
            flash(str(exc), "error")

    profile_error = None
    jd_error = None
    try:
        master = project_source_service.candidate_source()
    except (OSError, ValueError) as exc:
        master = None
        profile_error = str(exc)
    existing = project_source_service.existing_candidate(master) if master else None
    try:
        jd = project_source_service.jd_source()
    except (OSError, ValueError) as exc:
        jd = None
        jd_error = str(exc)
    return render_template(
        "pages/project_sources.html",
        master=master,
        existing=existing,
        jd=jd,
        profile_error=profile_error,
        jd_error=jd_error,
        candidates=candidate_service.list_profiles(),
        family_options=family_options(),
    )


def _matched_for(candidate_id: str | None):
    candidates = candidate_service.list_profiles()
    selected = None
    matched = []
    ready_count = 0
    summary = None
    if candidate_id:
        try:
            selected = candidate_service.get_profile(candidate_id)
            jobs = job_service.list_jobs_lite(limit=2000)
            summary = match_service.match_summary_for_candidate(selected, jobs)
            matched = summary["matches"]
            ready_count = summary["resume_ready_matches"]
        except KeyError:
            selected = None
    return candidates, selected, matched, ready_count, summary


@bp.route("/", methods=["GET", "POST"])
@require_auth
@csrf_protect
def index():
    candidates = candidate_service.list_profiles()
    candidate_id = request.values.get("candidate") or request.form.get("candidate_id")
    if not candidate_id and candidates:
        candidate_id = candidates[0]["id"]

    if request.method == "POST" and request.form.get("action") in {"generate", "local_draft"}:
        try:
            job = create_resume_service.start_create_resume(
                candidate_id=request.form.get("candidate_id") or "",
                jd_id=request.form.get("jd_id") or "",
                variants=int(request.form.get("variants") or 1),
                repair=request.form.get("repair") == "on",
                laya=request.form.get("laya") == "on",
                export_docx=request.form.get("docx") == "on",
                export_pdf=request.form.get("pdf") == "on",
                model=request.form.get("model") or None,
                local_draft=request.form.get("action") == "local_draft",
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
                flash("Preparing job analysis failed. Use Build Job Analysis / Rebuild Analysis.", "error")
            else:
                flash(text, "error")

    candidates, selected, matched, ready_count, summary = _matched_for(candidate_id)
    preselect_jd = request.args.get("jd") or request.form.get("jd_id")
    first_ready_id = next((m["id"] for m in matched if m.get("is_resume_ready")), None)
    return render_template(
        "pages/create.html",
        candidates=candidates,
        selected=selected,
        matched=matched,
        ready_count=ready_count,
        summary=summary,
        preselect_jd=preselect_jd,
        first_ready_id=first_ready_id,
        model_options=openai_command_service.model_options(),
        selected_resume_model=config_service.get_effective_setting("openai_resume_generation_model"),
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
    try:
        job = job_service.get_job(job_id)
        missing = job_service.validate_required_intake(job)
        if missing:
            flash(f"Preparing job analysis blocked. Required job intake missing: {', '.join(missing)}", "error")
            return redirect(url_for("create_resume.index", candidate=candidate_id, jd=job_id))
    except KeyError:
        flash("Job does not exist", "error")
        return redirect(url_for("create_resume.index", candidate=candidate_id))
    flash("Preparing job analysis...", "info")
    result = ensure_job_blueprint(job_id, actor=session.get("username"))
    if result.get("ok"):
        if result.get("fallback"):
            flash(
                "Job ready using local Laya fallback. OpenAI was unavailable for JD analysis; final resume generation may still need OpenAI credits/key.",
                "success",
            )
        else:
            flash("Job ready to generate.", "success")
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
