"""Matches — primary page: candidate selector → family-matched jobs."""

from __future__ import annotations

from flask import Blueprint, render_template, request

from resume_engine.ui.auth import require_auth
from resume_engine.ui.services import candidate_service, job_service, match_service
from resume_engine.ui.services.family_registry_service import display_name

bp = Blueprint("matches", __name__, url_prefix="/matches")


@bp.get("/")
@require_auth
def index():
    candidates = candidate_service.list_profiles()
    candidate_id = request.args.get("candidate") or (candidates[0]["id"] if candidates else None)
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
    return render_template(
        "pages/matches.html",
        candidates=candidates,
        selected=selected,
        matched=matched,
        family_display=display_name,
    )
