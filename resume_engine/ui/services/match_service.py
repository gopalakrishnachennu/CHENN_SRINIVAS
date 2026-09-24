"""Authoritative candidate ↔ job family matching (single source of truth).

All UI pages must use match_candidate_to_job / list_matches_for_candidate.
Persisted match_cache is optional and always version-gated.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from resume_engine.ui.db import connect_ui_db, ensure_ui_schema
from resume_engine.ui.services.family_registry_service import (
    display_name,
    get_family,
    resolve_family,
)

MATCH_DIRECT = "DIRECT"
MATCH_HYBRID = "HYBRID"
MATCH_SECONDARY = "SECONDARY"
MATCH_COMPATIBLE = "COMPATIBLE"
MATCH_NONE = "NO_MATCH"

# Compatibility aliases used by older callers
MATCH_TYPES = (MATCH_DIRECT, MATCH_HYBRID, MATCH_SECONDARY, MATCH_COMPATIBLE, MATCH_NONE)


@dataclass
class MatchResult:
    match_type: str
    score: float
    reason: str
    candidate_primary: str | None = None
    candidate_secondary: str | None = None
    job_primary: str | None = None
    job_secondary: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def is_match(self) -> bool:
        return self.match_type != MATCH_NONE


def _now() -> str:
    return datetime.now(UTC).isoformat()


def normalize_family_id(raw: Any) -> str | None:
    """Normalize family to canonical id or None (never '', 'None', 'null')."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text or text.lower() in {"none", "null", "n/a", "-"}:
        return None
    return resolve_family(text) or (text if text else None)


def _family_sets(
    candidate_primary: str | None,
    candidate_secondary: str | None,
    job_primary: str | None,
    job_secondary: str | None,
) -> tuple[set[str], set[str]]:
    cand = {x for x in (candidate_primary, candidate_secondary) if x}
    job = {x for x in (job_primary, job_secondary) if x}
    return cand, job


def _is_blocked(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    try:
        af = get_family(a)
    except KeyError:
        return False
    try:
        bf = get_family(b)
    except KeyError:
        return False
    return b in (af.get("blocked") or []) or a in (bf.get("blocked") or [])


def match_candidate_to_job(candidate: dict[str, Any], job: dict[str, Any]) -> MatchResult:
    """ONE authoritative matching function for the whole product."""
    payload = candidate.get("payload") or candidate
    cp = normalize_family_id(payload.get("primary_family") or candidate.get("primary_family"))
    cs = normalize_family_id(payload.get("secondary_family") or candidate.get("secondary_family"))
    jp = normalize_family_id(job.get("primary_family"))
    js = normalize_family_id(job.get("secondary_family"))

    if not cp or not jp:
        return MatchResult(MATCH_NONE, 0.0, "missing_primary_family", cp, cs, jp, js)

    if _is_blocked(cp, jp) or _is_blocked(cp, js) or _is_blocked(cs, jp):
        return MatchResult(MATCH_NONE, 0.0, "blocked_family_relationship", cp, cs, jp, js)

    # DIRECT
    if cp == jp:
        return MatchResult(MATCH_DIRECT, 1.0, "primary_equals_primary", cp, cs, jp, js)

    # SECONDARY — candidate secondary == JD primary
    if cs is not None and cs == jp:
        return MatchResult(MATCH_SECONDARY, 0.7, "candidate_secondary_equals_jd_primary", cp, cs, jp, js)

    # HYBRID — nonempty overlap of current family sets (not DIRECT)
    cand_set, job_set = _family_sets(cp, cs, jp, js)
    overlap = cand_set & job_set
    if overlap:
        # Require registry hybrid permission when both sides differ on primary
        try:
            cp_fam = get_family(cp)
            hybrid_ok = jp in (cp_fam.get("hybrid") or []) or any(
                x in (cp_fam.get("hybrid") or []) for x in job_set if x != jp
            )
        except KeyError:
            hybrid_ok = bool(overlap)
        if hybrid_ok or (js and js in cand_set) or (cs and cs in job_set):
            return MatchResult(
                MATCH_HYBRID,
                0.85,
                "family_overlap",
                cp,
                cs,
                jp,
                js,
            )

    # COMPATIBLE — explicit registry only (candidate primary → job primary)
    try:
        cp_fam = get_family(cp)
        if jp in (cp_fam.get("compatible") or []):
            return MatchResult(MATCH_COMPATIBLE, 0.5, "registry_compatible", cp, cs, jp, js)
    except KeyError:
        pass
    if cs:
        try:
            cs_fam = get_family(cs)
            if jp in (cs_fam.get("compatible") or []):
                return MatchResult(MATCH_COMPATIBLE, 0.5, "secondary_registry_compatible", cp, cs, jp, js)
        except KeyError:
            pass

    return MatchResult(MATCH_NONE, 0.0, "no_rule_matched", cp, cs, jp, js)


# --- Back-compat wrappers ---

def compute_match_type(
    candidate_primary: str,
    candidate_secondary: str | None,
    job_primary: str,
    job_secondary: str | None,
) -> dict[str, Any]:
    result = match_candidate_to_job(
        {"primary_family": candidate_primary, "secondary_family": candidate_secondary},
        {"primary_family": job_primary, "secondary_family": job_secondary},
    )
    return result.to_dict()


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


def list_matches_for_candidate(
    candidate: dict[str, Any],
    jobs: list[dict[str, Any]] | None = None,
    *,
    include_no_match: bool = False,
) -> list[dict[str, Any]]:
    """Live matches from current authoritative candidate + job records."""
    if jobs is None:
        from resume_engine.ui.services.job_service import list_jobs

        jobs = list_jobs(status="active", limit=5000)
    out: list[dict[str, Any]] = []
    for job in jobs:
        if (job.get("status") or "active") == "archived":
            continue
        result = match_candidate_to_job(candidate, job)
        if not include_no_match and not result.is_match:
            continue
        item = dict(job)
        item["match_type"] = result.match_type
        item["match_reason"] = result.reason
        item["match_score"] = result.score
        item["primary_family_display"] = display_name(job.get("primary_family"))
        item["secondary_family_display"] = display_name(job.get("secondary_family"))
        item["analysis_status"] = (job.get("analysis_status") or job.get("status") or "NEEDS_ANALYSIS")
        out.append(item)
    order = {MATCH_DIRECT: 0, MATCH_HYBRID: 1, MATCH_SECONDARY: 2, MATCH_COMPATIBLE: 3}
    out.sort(key=lambda x: (order.get(x["match_type"], 9), x.get("title") or ""))
    return out


def matches_for_candidate(candidate: dict[str, Any], jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return list_matches_for_candidate(candidate, jobs)


def count_matches_for_candidate(candidate: dict[str, Any], jobs: list[dict[str, Any]]) -> int:
    return len(list_matches_for_candidate(candidate, jobs))


def family_registry_version() -> str:
    ensure_ui_schema()
    with connect_ui_db() as conn:
        row = conn.execute(
            "SELECT MAX(updated_at) AS v FROM family_registry"
        ).fetchone()
    return str((row["v"] if row else None) or "0")


def invalidate_matches_for_candidate(candidate_id: str) -> int:
    ensure_ui_schema()
    with connect_ui_db() as conn:
        cur = conn.execute("DELETE FROM match_cache WHERE candidate_id = ?", (candidate_id,))
        conn.commit()
        return cur.rowcount


def invalidate_matches_for_job(job_id: str) -> int:
    ensure_ui_schema()
    with connect_ui_db() as conn:
        cur = conn.execute("DELETE FROM match_cache WHERE job_id = ?", (job_id,))
        conn.commit()
        return cur.rowcount


def invalidate_all_matches() -> int:
    ensure_ui_schema()
    with connect_ui_db() as conn:
        cur = conn.execute("DELETE FROM match_cache")
        conn.commit()
        return cur.rowcount


def recompute_and_cache_matches(candidate_id: str, *, actor: str | None = None) -> list[dict[str, Any]]:
    """Optional cache rewrite from live matching (version-stamped)."""
    from resume_engine.ui.services.candidate_service import get_profile
    from resume_engine.ui.services.job_service import list_jobs

    candidate = get_profile(candidate_id)
    jobs = list_jobs(status="active", limit=5000)
    matches = list_matches_for_candidate(candidate, jobs)
    cand_ver = int(candidate.get("version") or 1)
    fam_ver = family_registry_version()
    now = _now()
    ensure_ui_schema()
    with connect_ui_db() as conn:
        conn.execute("DELETE FROM match_cache WHERE candidate_id = ?", (candidate_id,))
        for m in matches:
            job_ver = int(m.get("analysis_version") or 0)
            details = {
                **{k: m.get(k) for k in ("match_type", "match_reason", "match_score", "title", "company")},
                "candidate_version": cand_ver,
                "job_analysis_version": job_ver,
                "family_registry_version": fam_ver,
            }
            conn.execute(
                """
                INSERT INTO match_cache(
                  candidate_id, job_id, match_type, score, details_json, created_at,
                  candidate_version, job_analysis_version, family_registry_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate_id,
                    m["id"],
                    m["match_type"],
                    m.get("match_score") or 0,
                    json.dumps(details),
                    now,
                    cand_ver,
                    job_ver,
                    fam_ver,
                ),
            )
        conn.commit()
    return matches


# Legacy names kept for imports
def match_candidate_to_jobs(
    candidate_id: str,
    candidate_primary: str,
    candidate_secondary: str | None,
    jobs: list[dict[str, Any]],
    *,
    actor: str | None = None,
) -> list[dict[str, Any]]:
    candidate = {
        "id": candidate_id,
        "primary_family": candidate_primary,
        "secondary_family": candidate_secondary,
    }
    results = []
    for job in jobs:
        result = match_candidate_to_job(candidate, job)
        results.append({
            **result.to_dict(),
            "candidate_id": candidate_id,
            "job_id": job.get("id"),
            "job_title": job.get("title"),
            "job_company": job.get("company"),
            "job_primary_family": job.get("primary_family"),
        })
    return results


def matched_jobs_for_candidate(
    candidate_id: str, candidate_primary: str, candidate_secondary: str | None
) -> list[dict[str, Any]]:
    from resume_engine.ui.services.candidate_service import get_profile

    try:
        candidate = get_profile(candidate_id)
    except KeyError:
        candidate = {
            "id": candidate_id,
            "payload": {
                "primary_family": candidate_primary,
                "secondary_family": candidate_secondary,
            },
        }
    return list_matches_for_candidate(candidate)


def get_cached_matches(candidate_id: str) -> list[dict[str, Any]]:
    """Return cache only if versions still match; else live recompute."""
    from resume_engine.ui.services.candidate_service import get_profile

    try:
        candidate = get_profile(candidate_id)
    except KeyError:
        return []
    cand_ver = int(candidate.get("version") or 1)
    fam_ver = family_registry_version()
    ensure_ui_schema()
    with connect_ui_db() as conn:
        rows = conn.execute(
            "SELECT * FROM match_cache WHERE candidate_id = ?",
            (candidate_id,),
        ).fetchall()
    fresh = []
    for r in rows:
        details = json.loads(r["details_json"] or "{}")
        if int(r["candidate_version"] or 0) != cand_ver:
            continue
        if str(r["family_registry_version"] or "") != fam_ver:
            continue
        fresh.append({
            "candidate_id": r["candidate_id"],
            "job_id": r["job_id"],
            "match_type": r["match_type"],
            "score": r["score"],
            **details,
        })
    if not fresh and rows:
        return recompute_and_cache_matches(candidate_id)
    return fresh


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
        }
        for r in rows
    ]
