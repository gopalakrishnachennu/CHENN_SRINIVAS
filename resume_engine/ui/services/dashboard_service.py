"""Simplified operator dashboard — product metrics only."""

from __future__ import annotations

from typing import Any

from resume_engine.ui.services import candidate_service, job_service, match_service, run_service


def dashboard_payload() -> dict[str, Any]:
    candidates = candidate_service.list_profiles()
    jobs = job_service.list_jobs_lite(limit=5000)
    runs = []
    try:
        runs = run_service.list_runs(limit=200)
    except Exception:  # noqa: BLE001
        runs = []

    validated = sum(1 for r in runs if str(r.get("status") or "").lower() in {"validated", "completed", "pass"})
    needs_attention = sum(
        1 for r in runs if str(r.get("status") or "").lower() in {"failed", "rejected", "error"}
    )

    recent_matches = []
    total_new = 0
    for cand in candidates[:12]:
        summary = match_service.match_summary_for_candidate(cand, jobs)
        matched = summary["matches"]
        created = cand.get("created_at") or ""
        new_count = sum(1 for m in matched if (m.get("updated_at") or "") > created)
        total_new += new_count
        recent_matches.append({
            "id": cand["id"],
            "name": cand["name"],
            "family": cand.get("primary_family_display"),
            "secondary": cand.get("secondary_family_display"),
            "match_count": summary["matched_jobs"],
            "new_count": new_count,
        })

    return {
        "candidates": len(candidates),
        "active_jds": len(jobs),
        "new_matches": total_new,
        "resumes_generated": len(runs),
        "validated_resumes": validated,
        "needs_attention": needs_attention,
        "recent_matches": recent_matches,
    }


def system_status_lite() -> dict[str, str]:
    """Non-technical health for advanced only — not shown on simple dashboard."""
    import os

    return {
        "openai": "CONFIGURED" if os.getenv("OPENAI_API_KEY") else "NOT CONFIGURED",
        "river": "SHADOW",
    }
