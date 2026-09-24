"""Deterministic family-based matching — DIRECT/HYBRID/SECONDARY/COMPATIBLE/NO MATCH.

Laya may validate ambiguous classifications but cannot override blocked relationships.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from resume_engine.ui.db import connect_ui_db, ensure_ui_schema
from resume_engine.ui.services.audit_service import record_audit_event
from resume_engine.ui.services.family_registry_service import get_family

MATCH_TYPES = ("DIRECT", "HYBRID", "SECONDARY", "COMPATIBLE", "NO_MATCH")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def compute_match_type(
    candidate_primary: str,
    candidate_secondary: str | None,
    job_primary: str,
    job_secondary: str | None,
) -> dict[str, Any]:
    """Deterministic family matching. Returns match_type + details."""
    if not candidate_primary or not job_primary:
        return {"match_type": "NO_MATCH", "score": 0.0, "reason": "Missing family data"}

    try:
        job_fam = get_family(job_primary)
    except KeyError:
        return {
            "match_type": "NO_MATCH", "score": 0.0,
            "reason": f"Unknown job family: {job_primary}",
        }

    blocked = job_fam.get("blocked") or []
    if candidate_primary in blocked:
        return {
            "match_type": "NO_MATCH",
            "score": 0.0,
            "reason": f"Blocked: {candidate_primary} → {job_primary}",
        }

    # DIRECT: candidate primary == job primary
    if candidate_primary == job_primary:
        return {"match_type": "DIRECT", "score": 1.0, "reason": "Primary family match"}

    # HYBRID: candidate primary is in the job family's hybrid list
    hybrid = job_fam.get("hybrid") or []
    if candidate_primary in hybrid:
        return {
            "match_type": "HYBRID",
            "score": 0.85,
            "reason": f"Hybrid match: {candidate_primary} in {job_primary} hybrid list",
        }

    # SECONDARY: candidate secondary matches job primary, or candidate primary matches job secondary
    if candidate_secondary and candidate_secondary == job_primary:
        return {
            "match_type": "SECONDARY",
            "score": 0.7,
            "reason": f"Candidate secondary ({candidate_secondary}) matches job primary",
        }
    if job_secondary and job_secondary != "none" and candidate_primary == job_secondary:
        return {
            "match_type": "SECONDARY",
            "score": 0.7,
            "reason": f"Candidate primary matches job secondary ({job_secondary})",
        }

    # COMPATIBLE: candidate primary is in the job family's compatible list
    compatible = job_fam.get("compatible") or []
    if candidate_primary in compatible:
        return {
            "match_type": "COMPATIBLE",
            "score": 0.5,
            "reason": f"Compatible: {candidate_primary} in {job_primary} compatible list",
        }

    return {"match_type": "NO_MATCH", "score": 0.0, "reason": "No family relationship found"}


def match_candidate_to_jobs(
    candidate_id: str,
    candidate_primary: str,
    candidate_secondary: str | None,
    jobs: list[dict[str, Any]],
    *,
    actor: str | None = None,
) -> list[dict[str, Any]]:
    """Match one candidate against a list of jobs. Stores results in match_cache."""
    ensure_ui_schema()
    results = []
    now = _now()

    with connect_ui_db() as conn:
        for job in jobs:
            job_id = job["id"]
            job_pf = job.get("primary_family") or ""
            job_sf = job.get("secondary_family")

            match = compute_match_type(
                candidate_primary, candidate_secondary, job_pf, job_sf
            )
            match["candidate_id"] = candidate_id
            match["job_id"] = job_id
            match["job_title"] = job.get("title")
            match["job_company"] = job.get("company")
            match["job_primary_family"] = job_pf

            conn.execute(
                """
                INSERT INTO match_cache(
                  candidate_id, job_id, match_type,
                  score, details_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(candidate_id, job_id) DO UPDATE SET
                  match_type=excluded.match_type,
                  score=excluded.score,
                  details_json=excluded.details_json,
                  created_at=excluded.created_at
                """,
                (
                    candidate_id, job_id, match["match_type"],
                    match["score"], json.dumps(match), now,
                ),
            )
            results.append(match)
        conn.commit()

    record_audit_event(
        action="match.compute",
        actor=actor,
        entity_type="match_cache",
        entity_id=candidate_id,
        metadata={
            "job_count": len(jobs),
            "match_count": sum(
                1 for r in results if r["match_type"] != "NO_MATCH"
            ),
        },
    )
    return results


def get_cached_matches(candidate_id: str) -> list[dict[str, Any]]:
    ensure_ui_schema()
    with connect_ui_db() as conn:
        rows = conn.execute(
            "SELECT * FROM match_cache WHERE candidate_id = ? ORDER BY score DESC",
            (candidate_id,),
        ).fetchall()
    return [
        {
            "candidate_id": r["candidate_id"],
            "job_id": r["job_id"],
            "match_type": r["match_type"],
            "score": r["score"],
            **(json.loads(r["details_json"]) if r["details_json"] else {}),
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def list_all_matches(*, min_score: float = 0.0) -> list[dict[str, Any]]:
    ensure_ui_schema()
    with connect_ui_db() as conn:
        rows = conn.execute(
            "SELECT * FROM match_cache WHERE score >= ? ORDER BY score DESC",
            (min_score,),
        ).fetchall()
    return [
        {
            "candidate_id": r["candidate_id"],
            "job_id": r["job_id"],
            "match_type": r["match_type"],
            "score": r["score"],
            **(json.loads(r["details_json"]) if r["details_json"] else {}),
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def matched_jobs_for_candidate(
    candidate_id: str, candidate_primary: str,
    candidate_secondary: str | None,
) -> list[dict[str, Any]]:
    """Return jobs that have at least COMPATIBLE match. Used by Create Resume wizard."""
    from resume_engine.ui.services.job_service import list_jobs

    jobs = list_jobs()
    matches = match_candidate_to_jobs(
        candidate_id, candidate_primary, candidate_secondary, jobs
    )
    return [m for m in matches if m["match_type"] != "NO_MATCH"]


# --- Product UI compatibility aliases ---
MATCH_NONE = "NO_MATCH"
MATCH_DIRECT = "DIRECT"
MATCH_HYBRID = "HYBRID"
MATCH_SECONDARY = "SECONDARY"
MATCH_COMPATIBLE = "COMPATIBLE"


def classify_match(
    *,
    candidate_primary: str | None,
    candidate_secondary: str | None = None,
    jd_primary: str | None,
    jd_secondary: str | None = None,
) -> dict[str, Any]:
    return compute_match_type(
        candidate_primary or "",
        candidate_secondary,
        jd_primary or "",
        jd_secondary,
    )


def matches_for_candidate(
    candidate: dict[str, Any], jobs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return matched jobs enriched with match_type (for product Matches / Create pages)."""
    payload = candidate.get("payload") or candidate
    cp = payload.get("primary_family") or ""
    cs = payload.get("secondary_family") or None
    out = []
    for job in jobs:
        result = compute_match_type(
            cp, cs, job.get("primary_family") or "",
            job.get("secondary_family"),
        )
        if result["match_type"] == MATCH_NONE:
            continue
        item = dict(job)
        item["match_type"] = result["match_type"]
        item["match_reason"] = result.get("reason")
        item["match_score"] = result.get("score")
        from resume_engine.ui.services.family_registry_service import display_name
        item["primary_family_display"] = display_name(item.get("primary_family"))
        item["secondary_family_display"] = display_name(item.get("secondary_family"))
        out.append(item)
    order = {MATCH_DIRECT: 0, MATCH_HYBRID: 1, MATCH_SECONDARY: 2, MATCH_COMPATIBLE: 3}
    out.sort(key=lambda x: (order.get(x["match_type"], 9), x.get("title") or ""))
    return out


def count_matches_for_candidate(candidate: dict[str, Any], jobs: list[dict[str, Any]]) -> int:
    return len(matches_for_candidate(candidate, jobs))
