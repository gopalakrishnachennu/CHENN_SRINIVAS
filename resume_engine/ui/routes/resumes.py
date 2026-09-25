"""Resume library — product primary page."""

from __future__ import annotations

from flask import Blueprint, render_template, request

from resume_engine.ui.auth import require_auth
from resume_engine.ui.services import create_resume_service, generation_service, run_service

bp = Blueprint("resumes", __name__, url_prefix="/resumes")


@bp.get("/")
@require_auth
def index():
    items = create_resume_service.list_resume_library(limit=200)
    candidate = request.args.get("candidate")
    status = request.args.get("status")
    if candidate:
        items = [i for i in items if candidate.lower() in str(i.get("candidate") or "").lower()]
    if status:
        items = [i for i in items if status.lower() in str(i.get("status") or "").lower()]
    return render_template("pages/resumes.html", items=items, filters=request.args)


@bp.get("/<run_id>")
@require_auth
def detail(run_id: str):
    library = {r["run_id"]: r for r in create_resume_service.list_resume_library(500)}
    meta = library.get(run_id)
    # Also try resume_library id
    if meta is None:
        try:
            r = create_resume_service.get_resume(run_id)
            meta = {
                "run_id": r.get("run_id") or r["id"],
                "candidate": r.get("candidate_id"),
                "job_title": r.get("job_id"),
                "status": r.get("status"),
                "match_type": (r.get("payload") or {}).get("match_type"),
                "job_id": (r.get("payload") or {}).get("job_id_gen"),
                "jd_hash": None,
            }
        except KeyError:
            meta = None
    job = None
    if meta and meta.get("job_id"):
        try:
            job = generation_service.get_job(meta["job_id"])
        except KeyError:
            job = None
    artifacts = None
    variants = []
    if meta and meta.get("jd_hash"):
        try:
            artifacts = run_service.get_run(meta["jd_hash"], run_id)
            for path in (artifacts.get("artifacts") or {}).get("validated") or []:
                variants.append({"label": path.split("/")[-1], "path": path, "status": "VALIDATED"})
            if not variants:
                for path in (artifacts.get("artifacts") or {}).get("raw") or []:
                    if path.endswith("_fact_draft.json"):
                        variants.append({"label": path.split("/")[-1], "path": path, "status": "FACT DRAFT"})
            if not variants:
                for path in (artifacts.get("artifacts") or {}).get("rejected") or []:
                    variants.append({
                        "label": path.split("/")[-1],
                        "path": path, "status": "REJECTED",
                    })
        except FileNotFoundError:
            artifacts = None
    return render_template(
        "pages/resume_detail.html",
        meta=meta,
        job=job,
        artifacts=artifacts,
        variants=variants,
        show_details=request.args.get("details") == "1",
    )
