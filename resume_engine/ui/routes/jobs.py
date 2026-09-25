"""Jobs library — product primary page."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from resume_engine.ui.auth import require_auth
from resume_engine.ui.csrf import csrf_protect
from resume_engine.ui.services import candidate_service, job_service
from resume_engine.ui.services.family_registry_service import display_name, family_options

bp = Blueprint("jobs", __name__, url_prefix="/jobs")


def _actor():
    return session.get("username")


def _enrich(job: dict) -> dict:
    job = dict(job)
    job["primary_family_display"] = display_name(job.get("primary_family"))
    job["secondary_family_display"] = display_name(job.get("secondary_family"))
    review = job_service.workflow_review(job)
    job["laya_workflow_review"] = review
    job["workflow_readiness"] = review.get("readiness") or "UNKNOWN"
    job["human_review_count"] = len(review.get("human_review_queue") or [])
    return job


@bp.get("/")
@require_auth
def index():
    raw = job_service.list_jobs(limit=2000)
    q = (request.args.get("q") or "").lower()
    family = request.args.get("family") or ""
    company = (request.args.get("company") or "").lower()
    location = (request.args.get("location") or "").lower()
    country = (request.args.get("country") or "").lower()
    state = (request.args.get("state") or "").lower()
    city = (request.args.get("city") or "").lower()
    work_mode = request.args.get("work_mode") or ""
    employment_type = request.args.get("employment_type") or ""
    engagement_type = request.args.get("engagement_type") or ""
    salary_status = request.args.get("salary_status") or ""
    sponsorship_status = request.args.get("sponsorship_status") or ""
    authorization_requirement = request.args.get("authorization_requirement") or ""
    student_visa_status = request.args.get("student_visa_status") or ""
    clearance_status = request.args.get("clearance_status") or ""
    min_experience = request.args.get("min_experience") or ""
    max_experience = request.args.get("max_experience") or ""
    status_filter = request.args.get("status") or ""
    jobs = []
    candidates = candidate_service.list_profiles()
    min_experience_num = _to_float(min_experience)
    max_experience_num = _to_float(max_experience)
    for job in raw:
        if family and family not in {job.get("primary_family"), job.get("secondary_family")}:
            continue
        if company and company not in (job.get("company") or "").lower():
            continue
        if location and location not in (job.get("location") or "").lower():
            continue
        if country and country not in (job.get("country") or "").lower():
            continue
        if state and state not in (job.get("state") or "").lower():
            continue
        if city and city not in (job.get("city") or "").lower():
            continue
        if work_mode and work_mode != (job.get("work_mode") or "UNKNOWN"):
            continue
        if employment_type and employment_type != (job.get("employment_type") or "UNKNOWN"):
            continue
        if engagement_type and engagement_type != (job.get("engagement_type") or "UNKNOWN"):
            continue
        if salary_status == "STATED" and job.get("salary_min") is None:
            continue
        if salary_status == "NOT_STATED" and job.get("salary_min") is not None:
            continue
        if sponsorship_status and sponsorship_status != (job.get("sponsorship_status") or "SPONSORSHIP_NOT_STATED"):
            continue
        if authorization_requirement and authorization_requirement != (job.get("authorization_requirement") or "NONE_STATED"):
            continue
        if student_visa_status and student_visa_status != (job.get("student_visa_status") or "OPT_CPT_NOT_STATED"):
            continue
        if clearance_status and clearance_status != (job.get("clearance_status") or "NOT_STATED"):
            continue
        years = job.get("minimum_years_experience")
        if min_experience_num is not None and (years is None or float(years) < min_experience_num):
            continue
        if max_experience_num is not None and (years is None or float(years) > max_experience_num):
            continue
        if status_filter and status_filter != (job.get("analysis_status") or "NEEDS_ANALYSIS"):
            continue
        if q and q not in f"{job.get('title')} {job.get('company')} {job.get('jd_text')}".lower():
            continue
        item = _enrich(job)
        item["candidates_matched"] = job_service.count_candidates_matched(job, candidates)
        jobs.append(item)
    stats = {
        "total": len(jobs),
        "ready": sum(1 for job in jobs if (job.get("analysis_status") or "").upper() == "READY"),
        "needs_review": sum(
            1
            for job in jobs
            if (job.get("analysis_status") or "NEEDS_ANALYSIS").upper()
            in {"NEEDS_ANALYSIS", "FAILED"}
        ),
        "remote_hybrid": sum(
            1 for job in jobs if (job.get("work_mode") or "").upper() in {"REMOTE", "HYBRID"}
        ),
        "visa_sensitive": sum(
            1
            for job in jobs
            if (job.get("sponsorship_status") or "") == "NO_SPONSORSHIP"
            or (job.get("authorization_requirement") or "")
            in {"US_CITIZEN_OR_GREEN_CARD", "AUTHORIZED_TO_WORK_US"}
        ),
        "manual_overrides": sum(
            len((job.get("job_intelligence") or {}).get("manual_overrides") or [])
            for job in jobs
        ),
        "laya_review": sum(
            1
            for job in jobs
            if (job.get("laya_workflow_review") or {}).get("human_review_required")
        ),
    }
    return render_template(
        "pages/jobs.html",
        jobs=jobs,
        stats=stats,
        family_options=family_options(),
        filters=request.args,
    )


@bp.route("/new", methods=["GET", "POST"])
@require_auth
@csrf_protect
def create():
    if request.method == "POST":
        action = request.form.get("action") or "analyze"
        payload = _job_intake_payload(request.form)
        jd_text = payload["jd_text"]
        upload = request.files.get("jd_file")
        if upload and upload.filename:
            flash("File upload is disabled for Phase 3.3. Paste the raw JD text manually.", "error")
            return render_template(
                "pages/job_new.html",
                analysis=None,
                form_values=payload,
                required_missing=[],
                required_fields=job_service.REQUIRED_JOB_INTAKE_FIELDS,
            )
        required_missing = job_service.validate_required_intake(payload)
        if required_missing:
            flash(f"Required job intake fields missing: {', '.join(required_missing)}", "error")
            return render_template(
                "pages/job_new.html",
                analysis=None,
                form_values=payload,
                required_missing=required_missing,
                required_fields=job_service.REQUIRED_JOB_INTAKE_FIELDS,
            )
        else:
            try:
                if action == "draft":
                    job = job_service.create_draft(
                        jd_text,
                        title=payload["title"],
                        company=payload["company"],
                        location=payload["location"],
                        job_url=payload["job_url"],
                        source=payload["source"] or "manual",
                        actor=_actor(),
                    )
                    flash("Job draft saved. Analyze when ready.", "success")
                    return redirect(url_for("jobs.detail", job_id=job["id"]))
                analysis = job_service.analyze_and_save(
                    jd_text,
                    title=payload["title"],
                    company=payload["company"],
                    location=payload["location"],
                    job_url=payload["job_url"],
                    source=payload["source"] or "manual",
                    actor=_actor(),
                )
                flash("Job analyzed and saved", "success")
                return redirect(url_for("jobs.detail", job_id=analysis["job"]["id"]))
            except Exception as exc:  # noqa: BLE001
                flash(str(exc), "error")
    form_values = payload if request.method == "POST" else {}
    if request.method == "GET" and request.args.get("from_project_jd") == "1":
        from resume_engine.ui.services.project_source_service import jd_source

        form_values = jd_source() or {}
    return render_template(
        "pages/job_new.html",
        analysis=None,
        form_values=form_values,
        required_missing=[],
        required_fields=job_service.REQUIRED_JOB_INTAKE_FIELDS,
    )


# Alias used by older links
@bp.route("/analyze", methods=["GET", "POST"])
@require_auth
@csrf_protect
def analyze():
    return create()


@bp.post("/analyze-pending")
@require_auth
@csrf_protect
def analyze_pending():
    from resume_engine.ui.services.blueprint_lifecycle import (
        ANALYSIS_FAILED,
        ANALYSIS_NEEDS,
        ensure_job_blueprint,
    )

    jobs = job_service.list_jobs(limit=5000)
    handled = 0
    failed = 0
    blocked = 0
    for job in jobs:
        status = (job.get("analysis_status") or "").upper()
        if status in {ANALYSIS_NEEDS, ANALYSIS_FAILED, ""}:
            if job_service.validate_required_intake(job):
                blocked += 1
                continue
            result = ensure_job_blueprint(job["id"], actor=_actor())
            handled += 1
            if not result.get("ok"):
                failed += 1
    if failed:
        flash(f"Analyzed {handled} jobs ({failed} failed, {blocked} missing required intake)", "error")
    elif blocked:
        flash(f"Analyzed {handled} pending jobs; {blocked} blocked by missing required intake", "error")
    else:
        flash(f"Analyzed {handled} pending jobs", "success")
    return redirect(url_for("jobs.index"))


@bp.get("/<job_id>")
@require_auth
def detail(job_id: str):
    job = _enrich(job_service.get_job(job_id))
    blueprint = job_service.load_blueprint(job) or {}
    if blueprint:
        public = job_service.public_analysis(blueprint)
        advanced = job_service.advanced_analysis(blueprint)
    else:
        display = job_service.get_job_display(job_id)
        public = {
            "target_role": job.get("title"),
            "seniority": job.get("seniority"),
            "primary_family_display": job.get("primary_family_display"),
            "secondary_family_display": job.get("secondary_family_display"),
            "must_have_skills": display.get("must_have") or [],
            "preferred_skills": display.get("preferred") or [],
            "responsibilities": display.get("responsibilities") or [],
            "certifications": display.get("certs") or [],
        }
        advanced = {
            "hybrid_probability": None,
            "p1": (job.get("metadata") or {}).get("p1") or [],
            "p2": (job.get("metadata") or {}).get("p2") or [],
            "p3": (job.get("metadata") or {}).get("p3") or [],
            "p4": [],
            "raw": job.get("metadata") or {},
        }
    matched_count = job_service.count_candidates_matched(job, candidate_service.list_profiles())
    required_missing = job_service.validate_required_intake(job)
    laya_review = job_service.workflow_review(job)
    return render_template(
        "pages/job_detail.html",
        job=job,
        intel=job.get("job_intelligence") or {},
        public=public,
        advanced=advanced,
        matched_count=matched_count,
        override_fields=job_service.OVERRIDE_FIELDS,
        overrides=job_service.list_manual_overrides(job_id),
        analysis_versions=job_service.list_analysis_versions(job_id),
        required_missing=required_missing,
        laya_review=laya_review,
        show_advanced=request.args.get("advanced") == "1",
    )


def _to_float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None


@bp.post("/<job_id>/override")
@require_auth
@csrf_protect
def override(job_id: str):
    field_name = request.form.get("field_name") or ""
    new_value = request.form.get("new_value") or ""
    reason = request.form.get("reason") or None
    try:
        job_service.apply_manual_override(
            job_id,
            field_name=field_name,
            new_value_raw=new_value,
            reason=reason,
            actor=_actor(),
        )
        flash(f"Manual override saved for {field_name}", "success")
    except Exception as exc:  # noqa: BLE001
        flash(str(exc), "error")
    return redirect(url_for("jobs.detail", job_id=job_id, advanced="1"))


@bp.route("/<job_id>/edit", methods=["GET", "POST"])
@require_auth
@csrf_protect
def edit(job_id: str):
    job = _enrich(job_service.get_job(job_id))
    if request.method == "POST":
        payload = _job_intake_payload(request.form)
        required_missing = job_service.validate_required_intake(payload)
        if required_missing:
            flash(f"Required job intake fields missing: {', '.join(required_missing)}", "error")
            return render_template(
                "pages/job_edit.html",
                job=job,
                intel=job.get("job_intelligence") or {},
                family_options=family_options(),
                form_values=payload,
                required_missing=required_missing,
                required_fields=job_service.REQUIRED_JOB_INTAKE_FIELDS,
            )
        job = job_service.update_job(
            job_id,
            {
                "title": payload["title"],
                "company": payload["company"],
                "location": payload["location"],
                "job_url": payload["job_url"],
                "jd_text": payload["jd_text"],
            },
            actor=_actor(),
        )
        flash("Job updated", "success")
        return redirect(url_for("jobs.detail", job_id=job["id"]))
    return render_template(
        "pages/job_edit.html",
        job=job,
        intel=job.get("job_intelligence") or {},
        family_options=family_options(),
        form_values={},
        required_missing=[],
        required_fields=job_service.REQUIRED_JOB_INTAKE_FIELDS,
    )


@bp.post("/<job_id>/reanalyze")
@require_auth
@csrf_protect
def reanalyze(job_id: str):
    from resume_engine.ui.services.blueprint_lifecycle import ensure_job_blueprint

    job = job_service.get_job(job_id)
    required_missing = job_service.validate_required_intake(job)
    if required_missing:
        flash(f"Cannot analyze until required job intake is complete: {', '.join(required_missing)}", "error")
        return redirect(url_for("jobs.detail", job_id=job_id))

    result = ensure_job_blueprint(job_id, actor=_actor(), force=True)
    if result.get("ok"):
        flash("Job re-analyzed", "success")
    else:
        flash(f"Analysis failed: {result.get('error') or result.get('reason')}", "error")
    return redirect(url_for("jobs.detail", job_id=job_id, advanced="1"))


@bp.get("/<job_id>/raw")
@require_auth
def raw_jd(job_id: str):
    job = _enrich(job_service.get_job(job_id))
    return render_template("pages/job_raw.html", job=job)


def _job_intake_payload(form) -> dict[str, str]:
    return {
        "title": (form.get("title") or "").strip(),
        "company": (form.get("company") or "").strip(),
        "location": (form.get("location") or "").strip(),
        "job_url": (form.get("job_url") or "").strip(),
        "source": (form.get("source") or "").strip(),
        "jd_text": (form.get("jd_text") or "").strip(),
    }


@bp.post("/<job_id>/archive")
@require_auth
@csrf_protect
def archive(job_id: str):
    job_service.archive_job(job_id, actor=_actor())
    flash("Job archived", "success")
    return redirect(url_for("jobs.index"))
