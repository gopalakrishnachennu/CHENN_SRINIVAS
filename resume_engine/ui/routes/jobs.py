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
    return job


@bp.get("/")
@require_auth
def index():
    raw = job_service.list_jobs(limit=2000)
    q = (request.args.get("q") or "").lower()
    family = request.args.get("family") or ""
    company = (request.args.get("company") or "").lower()
    location = (request.args.get("location") or "").lower()
    jobs = []
    candidates = candidate_service.list_profiles()
    for job in raw:
        if family and family not in {job.get("primary_family"), job.get("secondary_family")}:
            continue
        if company and company not in (job.get("company") or "").lower():
            continue
        if location and location not in (job.get("location") or "").lower():
            continue
        if q and q not in f"{job.get('title')} {job.get('company')} {job.get('jd_text')}".lower():
            continue
        item = _enrich(job)
        item["candidates_matched"] = job_service.count_candidates_matched(job, candidates)
        jobs.append(item)
    return render_template(
        "pages/jobs.html",
        jobs=jobs,
        family_options=family_options(),
        filters=request.args,
    )


@bp.route("/new", methods=["GET", "POST"])
@require_auth
@csrf_protect
def create():
    if request.method == "POST":
        jd_text = request.form.get("jd_text") or ""
        upload = request.files.get("jd_file")
        if upload and upload.filename:
            try:
                jd_text = job_service.extract_upload(upload.filename, upload.read())
            except Exception as exc:  # noqa: BLE001
                flash(str(exc), "error")
                return render_template("pages/job_new.html", analysis=None)
        if not jd_text.strip():
            flash("Paste or upload a job description first", "error")
        else:
            try:
                analysis = job_service.analyze_and_save(
                    jd_text,
                    company=request.form.get("company"),
                    location=request.form.get("location"),
                    job_url=request.form.get("job_url"),
                    source=request.form.get("source") or "manual",
                    actor=_actor(),
                )
                flash("Job analyzed and saved", "success")
                return redirect(url_for("jobs.detail", job_id=analysis["job"]["id"]))
            except Exception as exc:  # noqa: BLE001
                flash(str(exc), "error")
    return render_template("pages/job_new.html", analysis=None)


# Alias used by older links
@bp.route("/analyze", methods=["GET", "POST"])
@require_auth
@csrf_protect
def analyze():
    return create()


@bp.get("/<job_id>")
@require_auth
def detail(job_id: str):
    job = _enrich(job_service.get_job(job_id))
    blueprint = job_service.load_blueprint(job) or {}
    public = job_service.public_analysis(blueprint) if blueprint else {
        "target_role": job.get("title"),
        "seniority": job.get("seniority"),
        "primary_family_display": job.get("primary_family_display"),
        "secondary_family_display": job.get("secondary_family_display"),
        "must_have_skills": [],
        "preferred_skills": [],
        "responsibilities": [],
        "certifications": [],
    }
    # Prefer stored display when blueprint empty
    if not public.get("primary_family_display"):
        public["primary_family_display"] = job["primary_family_display"]
        public["secondary_family_display"] = job["secondary_family_display"]
    advanced = job_service.advanced_analysis(blueprint) if blueprint else {}
    matched_count = job_service.count_candidates_matched(job, candidate_service.list_profiles())
    return render_template(
        "pages/job_detail.html",
        job=job,
        public=public,
        advanced=advanced,
        matched_count=matched_count,
        show_advanced=request.args.get("advanced") == "1",
    )
