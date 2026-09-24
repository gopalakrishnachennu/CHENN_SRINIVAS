"""Authoritative candidate ↔ job family matching (strict by default).

Normal product surfaces (Dashboard, Matches, Create Resume) use STRICT mode:
DIRECT / SECONDARY / HYBRID exact-overlap only. COMPATIBLE is opt-in Advanced.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from resume_engine.ui.db import connect_ui_db, ensure_ui_schema

MATCH_DIRECT = "DIRECT"
MATCH_HYBRID = "HYBRID"
MATCH_SECONDARY = "SECONDARY"
MATCH_COMPATIBLE = "COMPATIBLE"
MATCH_NONE = "NO_MATCH"

MATCH_TYPES = (MATCH_DIRECT, MATCH_HYBRID, MATCH_SECONDARY, MATCH_COMPATIBLE, MATCH_NONE)
STRICT_MATCH_TYPES = {MATCH_DIRECT, MATCH_HYBRID, MATCH_SECONDARY}


@dataclass(frozen=True)
class FamilyRegistrySnapshot:
    """Immutable in-memory family registry for one match request (no N+1 SQL)."""

    family_by_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)  # lower alias/display → id
    display_names: dict[str, str] = field(default_factory=dict)
    version: str = "0"

    def resolve(self, raw: Any) -> str | None:
        if raw is None:
            return None
        text = str(raw).strip()
        if not text or text.lower() in {"none", "null", "n/a", "-"}:
            return None
        if text in self.family_by_id:
            return text
        return self.aliases.get(text.lower())

    def display(self, family_id: str | None) -> str:
        if not family_id:
            return ""
        return self.display_names.get(family_id, family_id)

    def get(self, family_id: str) -> dict[str, Any] | None:
        return self.family_by_id.get(family_id)

    def is_blocked(self, a: str | None, b: str | None) -> bool:
        if not a or not b:
            return False
        af = self.family_by_id.get(a) or {}
        bf = self.family_by_id.get(b) or {}
        return b in (af.get("blocked") or []) or a in (bf.get("blocked") or [])


def load_family_registry_snapshot() -> FamilyRegistrySnapshot:
    ensure_ui_schema()
    with connect_ui_db() as conn:
        rows = conn.execute("SELECT * FROM family_registry").fetchall()
        ver_row = conn.execute("SELECT MAX(updated_at) AS v FROM family_registry").fetchone()
    version = str((ver_row["v"] if ver_row else None) or "0")
    family_by_id: dict[str, dict[str, Any]] = {}
    aliases: dict[str, str] = {}
    display_names: dict[str, str] = {}
    for row in rows:
        fid = row["family_id"]
        data = {
            "family_id": fid,
            "display_name": row["display_name"],
            "aliases": json.loads(row["aliases_json"] or "[]"),
            "compatible": json.loads(row["compatible_json"] or "[]"),
            "hybrid": json.loads(row["hybrid_json"] or "[]"),
            "blocked": json.loads(row["blocked_json"] or "[]"),
            "status": row["status"],
        }
        family_by_id[fid] = data
        display_names[fid] = row["display_name"]
        aliases[fid.lower()] = fid
        aliases[row["display_name"].lower()] = fid
        for alias in data["aliases"]:
            aliases[str(alias).lower()] = fid
    return FamilyRegistrySnapshot(
        family_by_id=family_by_id,
        aliases=aliases,
        display_names=display_names,
        version=version,
    )


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

    @property
    def is_strict_match(self) -> bool:
        return self.match_type in STRICT_MATCH_TYPES


def _now() -> str:
    return datetime.now(UTC).isoformat()


def normalize_family_id(
    raw: Any,
    registry: FamilyRegistrySnapshot | None = None,
) -> str | None:
    if registry is None:
        registry = load_family_registry_snapshot()
    return registry.resolve(raw)


def match_candidate_to_job(
    candidate: dict[str, Any],
    job: dict[str, Any],
    *,
    registry: FamilyRegistrySnapshot | None = None,
    include_compatible: bool = False,
) -> MatchResult:
    """ONE authoritative matching function.

    Strict (default): DIRECT → SECONDARY → HYBRID exact-overlap → NO_MATCH.
    include_compatible=True enables registry COMPATIBLE (Advanced only).
    """
    reg = registry or load_family_registry_snapshot()
    payload = candidate.get("payload") or candidate
    cp = normalize_family_id(payload.get("primary_family") or candidate.get("primary_family"), reg)
    cs = normalize_family_id(payload.get("secondary_family") or candidate.get("secondary_family"), reg)
    jp = normalize_family_id(job.get("primary_family"), reg)
    js = normalize_family_id(job.get("secondary_family"), reg)

    if not cp or not jp:
        return MatchResult(MATCH_NONE, 0.0, "missing_primary_family", cp, cs, jp, js)

    if reg.is_blocked(cp, jp) or reg.is_blocked(cp, js) or reg.is_blocked(cs, jp):
        return MatchResult(MATCH_NONE, 0.0, "blocked_family_relationship", cp, cs, jp, js)

    # DIRECT
    if cp == jp:
        return MatchResult(MATCH_DIRECT, 1.0, "primary_equals_primary", cp, cs, jp, js)

    # SECONDARY — candidate secondary == JD primary
    if cs is not None and cs == jp:
        return MatchResult(MATCH_SECONDARY, 0.7, "candidate_secondary_equals_jd_primary", cp, cs, jp, js)

    # HYBRID — exact overlap of current family sets (not DIRECT)
    cand_set = {x for x in (cp, cs) if x}
    job_set = {x for x in (jp, js) if x}
    overlap = cand_set & job_set
    if overlap:
        return MatchResult(MATCH_HYBRID, 0.85, "family_overlap", cp, cs, jp, js)

    # COMPATIBLE — Advanced / opt-in only
    if include_compatible:
        cp_fam = reg.get(cp) or {}
        if jp in (cp_fam.get("compatible") or []):
            return MatchResult(MATCH_COMPATIBLE, 0.5, "registry_compatible", cp, cs, jp, js)
        if cs:
            cs_fam = reg.get(cs) or {}
            if jp in (cs_fam.get("compatible") or []):
                return MatchResult(
                    MATCH_COMPATIBLE, 0.5, "secondary_registry_compatible", cp, cs, jp, js
                )

    return MatchResult(MATCH_NONE, 0.0, "no_rule_matched", cp, cs, jp, js)


def compute_match_type(
    candidate_primary: str,
    candidate_secondary: str | None,
    job_primary: str,
    job_secondary: str | None,
    *,
    include_compatible: bool = False,
    registry: FamilyRegistrySnapshot | None = None,
) -> dict[str, Any]:
    result = match_candidate_to_job(
        {"primary_family": candidate_primary, "secondary_family": candidate_secondary},
        {"primary_family": job_primary, "secondary_family": job_secondary},
        include_compatible=include_compatible,
        registry=registry,
    )
    return result.to_dict()


def classify_match(
    *,
    candidate_primary: str | None,
    candidate_secondary: str | None = None,
    jd_primary: str | None,
    jd_secondary: str | None = None,
    include_compatible: bool = False,
) -> dict[str, Any]:
    return compute_match_type(
        candidate_primary or "",
        candidate_secondary,
        jd_primary or "",
        jd_secondary,
        include_compatible=include_compatible,
    )


def _job_is_resume_ready(job: dict[str, Any]) -> bool:
    """Lightweight readiness for match listing (no heavy JSON parse)."""
    if (job.get("status") or "active").lower() == "archived":
        return False
    status = (job.get("analysis_status") or "").upper()
    if status != "READY":
        return False
    path = job.get("blueprint_path")
    if not path:
        return False
    from pathlib import Path

    return Path(path).exists()


def list_matches_for_candidate(
    candidate: dict[str, Any],
    jobs: list[dict[str, Any]] | None = None,
    *,
    include_no_match: bool = False,
    include_compatible: bool = False,
    ready_only: bool = True,
    registry: FamilyRegistrySnapshot | None = None,
) -> list[dict[str, Any]]:
    """Live strict matches from current authoritative candidate + job records."""
    reg = registry or load_family_registry_snapshot()
    if jobs is None:
        from resume_engine.ui.services.job_service import list_jobs_lite

        jobs = list_jobs_lite(status="active", limit=5000)
    out: list[dict[str, Any]] = []
    for job in jobs:
        if (job.get("status") or "active") == "archived":
            continue
        if ready_only and not _job_is_resume_ready(job):
            continue
        result = match_candidate_to_job(
            candidate, job, registry=reg, include_compatible=include_compatible
        )
        if not include_no_match and not result.is_strict_match and not (
            include_compatible and result.match_type == MATCH_COMPATIBLE
        ):
            continue
        if not include_compatible and result.match_type == MATCH_COMPATIBLE:
            continue
        if not include_no_match and result.match_type == MATCH_NONE:
            continue
        item = dict(job)
        item["match_type"] = result.match_type
        item["match_reason"] = result.reason
        item["match_score"] = result.score
        item["primary_family_display"] = reg.display(job.get("primary_family"))
        item["secondary_family_display"] = reg.display(job.get("secondary_family"))
        item["analysis_status"] = job.get("analysis_status") or "NEEDS_ANALYSIS"
        out.append(item)
    order = {MATCH_DIRECT: 0, MATCH_HYBRID: 1, MATCH_SECONDARY: 2, MATCH_COMPATIBLE: 3}
    out.sort(key=lambda x: (order.get(x["match_type"], 9), x.get("title") or ""))
    return out


def match_summary_for_candidate(
    candidate: dict[str, Any],
    jobs: list[dict[str, Any]] | None = None,
    *,
    include_compatible: bool = False,
) -> dict[str, Any]:
    """Explainable match counts with distinct job IDs."""
    from resume_engine.ui.services.job_service import list_jobs_lite

    reg = load_family_registry_snapshot()
    if jobs is None:
        jobs = list_jobs_lite(status="active", limit=5000)
    active = [j for j in jobs if (j.get("status") or "active") != "archived"]
    ready = [j for j in active if _job_is_resume_ready(j)]
    needs = sum(
        1
        for j in active
        if (j.get("analysis_status") or "").upper() in {"NEEDS_ANALYSIS", "FAILED", "ANALYZING", ""}
    )
    matched = list_matches_for_candidate(
        candidate, ready, include_compatible=include_compatible, ready_only=True, registry=reg
    )
    # Deduplicate by job id
    by_id: dict[str, dict[str, Any]] = {}
    for m in matched:
        by_id[m["id"]] = m
    unique = list(by_id.values())
    direct = sum(1 for m in unique if m["match_type"] == MATCH_DIRECT)
    secondary = sum(1 for m in unique if m["match_type"] == MATCH_SECONDARY)
    hybrid = sum(1 for m in unique if m["match_type"] == MATCH_HYBRID)
    return {
        "total_jobs": len(active),
        "ready_jobs": len(ready),
        "needs_analysis_jobs": needs,
        "matched_jobs": len(unique),
        "direct": direct,
        "secondary": secondary,
        "hybrid": hybrid,
        "matches": unique,
    }


def matches_for_candidate(candidate: dict[str, Any], jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return list_matches_for_candidate(candidate, jobs, ready_only=True, include_compatible=False)


def count_matches_for_candidate(candidate: dict[str, Any], jobs: list[dict[str, Any]]) -> int:
    return len(list_matches_for_candidate(candidate, jobs, ready_only=True, include_compatible=False))


def family_registry_version() -> str:
    return load_family_registry_snapshot().version


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
    from resume_engine.ui.services.candidate_service import get_profile
    from resume_engine.ui.services.job_service import list_jobs_lite

    candidate = get_profile(candidate_id)
    jobs = list_jobs_lite(status="active", limit=5000)
    matches = list_matches_for_candidate(candidate, jobs, ready_only=True, include_compatible=False)
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


def match_candidate_to_jobs(
    candidate_id: str,
    candidate_primary: str,
    candidate_secondary: str | None,
    jobs: list[dict[str, Any]],
    *,
    actor: str | None = None,
    include_compatible: bool = False,
) -> list[dict[str, Any]]:
    reg = load_family_registry_snapshot()
    candidate = {
        "id": candidate_id,
        "primary_family": candidate_primary,
        "secondary_family": candidate_secondary,
    }
    results = []
    for job in jobs:
        result = match_candidate_to_job(
            candidate, job, registry=reg, include_compatible=include_compatible
        )
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
    return list_matches_for_candidate(candidate, ready_only=True, include_compatible=False)


def get_cached_matches(candidate_id: str) -> list[dict[str, Any]]:
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
