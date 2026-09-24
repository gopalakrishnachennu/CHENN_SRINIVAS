"""Matches — strict READY family matches, paginated, compact."""

from __future__ import annotations

from flask import Blueprint, render_template, request

from resume_engine.ui.auth import require_auth
from resume_engine.ui.services import candidate_service, job_service, match_service
from resume_engine.ui.services.family_registry_service import display_name, family_options

bp = Blueprint("matches", __name__, url_prefix="/matches")

PAGE_SIZE = 20


@bp.get("/")
@require_auth
def index():
    candidates = candidate_service.list_profiles()
    candidate_id = (
        request.args.get("candidate_id")
        or request.args.get("candidate")
        or (candidates[0]["id"] if candidates else None)
    )
    page = max(1, int(request.args.get("page") or 1))
    company_q = (request.args.get("company") or "").strip().lower()
    family_q = (request.args.get("family") or "").strip()
    match_type_q = (request.args.get("match_type") or "").strip().upper()
    include_adjacent = request.args.get("adjacent") == "1"

    selected = None
    summary = {
        "total_jobs": 0,
        "ready_jobs": 0,
        "needs_analysis_jobs": 0,
        "matched_jobs": 0,
        "direct": 0,
        "secondary": 0,
        "hybrid": 0,
        "matches": [],
    }
    page_matches = []
    total_pages = 1

    if candidate_id:
        try:
            selected = candidate_service.get_profile(candidate_id)
            jobs = job_service.list_jobs_lite(status="active", limit=5000)
            summary = match_service.match_summary_for_candidate(
                selected, jobs, include_compatible=include_adjacent
            )
            matched = summary["matches"]
            if company_q:
                matched = [m for m in matched if company_q in (m.get("company") or "").lower()]
            if family_q:
                matched = [
                    m
                    for m in matched
                    if family_q in {m.get("primary_family"), m.get("secondary_family")}
                ]
            if match_type_q:
                matched = [m for m in matched if (m.get("match_type") or "") == match_type_q]

            total = len(matched)
            total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
            page = min(page, total_pages)
            start = (page - 1) * PAGE_SIZE
            page_matches = matched[start : start + PAGE_SIZE]
            summary = {**summary, "matched_jobs": total, "matches": page_matches}
        except KeyError:
            selected = None

    return render_template(
        "pages/matches.html",
        candidates=candidates,
        selected=selected,
        summary=summary,
        matched=page_matches,
        page=page,
        total_pages=total_pages,
        page_size=PAGE_SIZE,
        family_display=display_name,
        family_options=family_options(),
        filters={
            "company": request.args.get("company") or "",
            "family": family_q,
            "match_type": match_type_q,
            "adjacent": include_adjacent,
        },
    )
