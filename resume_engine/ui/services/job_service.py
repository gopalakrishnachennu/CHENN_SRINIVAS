"""Job library service — wraps Phase 1 analysis into a persistent JD library."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from resume_engine.ui.db import connect_ui_db, ensure_ui_schema
from resume_engine.ui.services.audit_service import record_audit_event
from resume_engine.ui.services.family_registry_service import resolve_family


def _now() -> str:
    return datetime.now(UTC).isoformat()


def list_jobs(*, status: str = "active", limit: int = 100) -> list[dict[str, Any]]:
    ensure_ui_schema()
    with connect_ui_db() as conn:
        if status == "all":
            rows = conn.execute(
                "SELECT * FROM jd_library ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM jd_library WHERE status = ? ORDER BY updated_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
    return [_row_to_dict(r) for r in rows]


def list_jobs_lite(*, status: str = "active", limit: int = 5000) -> list[dict[str, Any]]:
    """Lightweight job rows for matching — no filesystem blueprint revalidation."""
    ensure_ui_schema()
    with connect_ui_db() as conn:
        if status == "all":
            rows = conn.execute(
                """
                SELECT id, title, company, location, primary_family, secondary_family,
                       status, analysis_status, analysis_version, blueprint_path,
                       jd_content_hash, job_url, seniority, source, updated_at
                FROM jd_library ORDER BY updated_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, title, company, location, primary_family, secondary_family,
                       status, analysis_status, analysis_version, blueprint_path,
                       jd_content_hash, job_url, seniority, source, updated_at
                FROM jd_library WHERE status = ? ORDER BY updated_at DESC LIMIT ?
                """,
                (status, limit),
            ).fetchall()
    out = []
    for row in rows:
        sf = row["secondary_family"]
        out.append({
            "id": row["id"],
            "title": row["title"],
            "company": row["company"],
            "location": row["location"],
            "primary_family": row["primary_family"],
            "secondary_family": None if sf in ("", "none", "null", None) else sf,
            "status": row["status"],
            "analysis_status": row["analysis_status"] or "NEEDS_ANALYSIS",
            "analysis_version": int(row["analysis_version"] or 0),
            "blueprint_path": row["blueprint_path"],
            "jd_content_hash": row["jd_content_hash"],
            "job_url": row["job_url"],
            "seniority": row["seniority"],
            "source": row["source"],
            "updated_at": row["updated_at"],
        })
    return out


def find_duplicate_job(
    *,
    jd_text: str | None = None,
    job_url: str | None = None,
    content_hash: str | None = None,
) -> dict[str, Any] | None:
    """Return existing job if content hash or canonical URL already present."""
    from resume_engine.ui.services.blueprint_lifecycle import jd_content_hash

    ensure_ui_schema()
    url = (job_url or "").strip() or None
    ch = content_hash
    if not ch and jd_text:
        ch = jd_content_hash(jd_text)
    with connect_ui_db() as conn:
        if url:
            row = conn.execute(
                "SELECT id FROM jd_library WHERE job_url = ? AND status != 'archived' LIMIT 1",
                (url,),
            ).fetchone()
            if row:
                return get_job(row["id"])
        if ch:
            row = conn.execute(
                "SELECT id FROM jd_library WHERE jd_content_hash = ? AND status != 'archived' LIMIT 1",
                (ch,),
            ).fetchone()
            if row:
                return get_job(row["id"])
            # Also match on hash of stored jd_text when jd_content_hash unset
            rows = conn.execute(
                "SELECT id, jd_text FROM jd_library WHERE status != 'archived' AND jd_text IS NOT NULL"
            ).fetchall()
            for r in rows:
                if jd_content_hash(r["jd_text"] or "") == ch:
                    return get_job(r["id"])
    return None


def get_job(job_id: str) -> dict[str, Any]:
    ensure_ui_schema()
    with connect_ui_db() as conn:
        row = conn.execute(
            "SELECT * FROM jd_library WHERE id = ?", (job_id,)
        ).fetchone()
    if row is None:
        raise KeyError(job_id)
    return _row_to_dict(row)


def _row_to_dict(row) -> dict[str, Any]:
    keys = set(row.keys())
    from resume_engine.ui.services.blueprint_lifecycle import get_analysis_status

    base = {
        "id": row["id"],
        "jd_hash": row["jd_hash"],
        "title": row["title"],
        "company": row["company"],
        "location": row["location"],
        "job_url": row["job_url"],
        "source": row["source"],
        "seniority": row["seniority"],
        "primary_family": row["primary_family"],
        "secondary_family": row["secondary_family"] if row["secondary_family"] not in ("", "none", "null") else None,
        "status": row["status"],
        "blueprint_path": row["blueprint_path"],
        "jd_text": row["jd_text"],
        "metadata": json.loads(row["metadata_json"]) if row["metadata_json"] else {},
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "analysis_status": row["analysis_status"] if "analysis_status" in keys else None,
        "analysis_version": int(row["analysis_version"] or 0) if "analysis_version" in keys else 0,
        "jd_content_hash": row["jd_content_hash"] if "jd_content_hash" in keys else None,
    }
    # Effective readiness (validates blueprint file / staleness)
    base["analysis_status"] = get_analysis_status(base)
    return base


def analyze_and_store(
    jd_text: str,
    *,
    company: str | None = None,
    location: str | None = None,
    job_url: str | None = None,
    source: str = "manual",
    actor: str | None = None,
    allow_duplicate: bool = False,
) -> dict[str, Any]:
    """Run Phase 1 on JD text, store result in the JD library (deduped by default)."""
    from resume_engine.ui.services.blueprint_lifecycle import jd_content_hash
    from resume_engine.ui.services.jd_service import analyze_jd

    if not allow_duplicate:
        existing = find_duplicate_job(jd_text=jd_text, job_url=job_url)
        if existing is not None:
            return existing

    result = analyze_jd(jd_text, actor=actor)
    blueprint = result["blueprint"]
    bp_path = result["path"]
    job_data = blueprint.get("job") or {}

    job_id = str(uuid.uuid4())
    jd_hash = blueprint.get("jd_hash") or job_id[:12]
    title = job_data.get("target_title") or "Untitled Role"
    seniority = job_data.get("seniority") or "mid"
    pf = job_data.get("primary_family") or ""
    sf = job_data.get("secondary_family") or "none"

    primary_family = resolve_family(pf) or pf
    secondary_family = resolve_family(sf) or sf

    priority_skills = blueprint.get("priority_skills") or {}

    meta = {
        "hybrid_probability": job_data.get("hybrid_probability", 0),
        "p1": priority_skills.get("P1", []),
        "p2": priority_skills.get("P2", []),
        "p3": priority_skills.get("P3", []),
        "p4": priority_skills.get("P4", []),
        "generation_contract": blueprint.get("generation_contract"),
        "quality_gates": blueprint.get("quality_gates"),
        "full_blueprint": blueprint,
    }

    now = _now()
    ensure_ui_schema()
    from resume_engine.ui.services.blueprint_lifecycle import ANALYSIS_READY

    secondary_family = None if secondary_family in {"none", "null", None, ""} else secondary_family
    with connect_ui_db() as conn:
        conn.execute(
            """
            INSERT INTO jd_library(
              id, jd_hash, title, company, location, job_url, source,
              seniority, primary_family, secondary_family, status,
              blueprint_path, jd_text, metadata_json, created_at, updated_at,
              analysis_status, analysis_version, jd_content_hash
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                job_id, jd_hash, title, company, location, job_url, source,
                seniority, primary_family, secondary_family, "active",
                str(bp_path), jd_text, json.dumps(meta), now, now,
                ANALYSIS_READY, 1, jd_content_hash(jd_text),
            ),
        )
        conn.commit()

    record_audit_event(
        action="job.analyze_store",
        actor=actor,
        entity_type="jd_library",
        entity_id=job_id,
        metadata={"jd_hash": jd_hash, "title": title},
    )
    return get_job(job_id)


def update_job(
    job_id: str,
    updates: dict[str, Any],
    *,
    actor: str | None = None,
) -> dict[str, Any]:
    existing = get_job(job_id)
    now = _now()
    title = updates.get("title", existing["title"])
    company = updates.get("company", existing["company"])
    location = updates.get("location", existing["location"])
    seniority = updates.get("seniority", existing["seniority"])
    pf = updates.get("primary_family", existing["primary_family"])
    sf = updates.get("secondary_family", existing["secondary_family"])
    if sf in ("", "none", "null"):
        sf = None
    status = updates.get("status", existing["status"])
    new_jd_text = updates.get("jd_text")
    jd_text_changed = new_jd_text is not None and (new_jd_text or "") != (existing.get("jd_text") or "")

    with connect_ui_db() as conn:
        if jd_text_changed:
            from resume_engine.ui.services.blueprint_lifecycle import ANALYSIS_NEEDS

            conn.execute(
                """
                UPDATE jd_library SET
                  title=?, company=?, location=?, seniority=?,
                  primary_family=?, secondary_family=?, status=?,
                  jd_text=?, blueprint_path=NULL, analysis_status=?,
                  jd_content_hash=NULL, updated_at=?
                WHERE id=?
                """,
                (
                    title, company, location, seniority, pf, sf, status,
                    new_jd_text, ANALYSIS_NEEDS, now, job_id,
                ),
            )
        else:
            conn.execute(
                """
                UPDATE jd_library SET
                  title=?, company=?, location=?, seniority=?,
                  primary_family=?, secondary_family=?, status=?, updated_at=?
                WHERE id=?
                """,
                (title, company, location, seniority, pf, sf, status, now, job_id),
            )
        conn.commit()

    from resume_engine.ui.services import match_service

    family_changed = (
        pf != existing.get("primary_family")
        or sf != existing.get("secondary_family")
        or jd_text_changed
    )
    if family_changed:
        match_service.invalidate_matches_for_job(job_id)

    record_audit_event(
        action="job.update",
        actor=actor,
        entity_type="jd_library",
        entity_id=job_id,
        metadata={"jd_text_changed": jd_text_changed},
    )
    return get_job(job_id)


def archive_job(job_id: str, *, actor: str | None = None) -> None:
    update_job(job_id, {"status": "archived"}, actor=actor)
    from resume_engine.ui.services import match_service

    match_service.invalidate_matches_for_job(job_id)


def get_job_display(job_id: str) -> dict[str, Any]:
    """Return job data formatted for the normal (non-advanced) UI."""
    job = get_job(job_id)
    meta = job.get("metadata") or {}
    display = meta.get("display") or {}
    must_have = display.get("must_have") or (meta.get("p1", []) + meta.get("p2", []))
    preferred = display.get("preferred") or meta.get("p3", [])
    responsibilities = (
        display.get("responsibilities")
        or meta.get("full_blueprint", {}).get("responsibilities")
        or []
    )
    if isinstance(responsibilities, str):
        responsibilities = [s.strip() for s in responsibilities.split(";") if s.strip()]
    certs = meta.get("full_blueprint", {}).get("certifications") or []
    return {
        **job,
        "must_have": must_have,
        "preferred": preferred,
        "responsibilities": responsibilities,
        "certs": certs,
    }


def analyze_and_save(jd_text: str, **kwargs) -> dict[str, Any]:
    job = analyze_and_store(jd_text, **kwargs)
    display = get_job_display(job["id"])
    meta = job.get("metadata") or {}
    return {
        "job": {
            **job,
            "primary_family_display": __import__(
                "resume_engine.ui.services.family_registry_service", fromlist=["display_name"]
            ).display_name(job.get("primary_family")),
            "secondary_family_display": __import__(
                "resume_engine.ui.services.family_registry_service", fromlist=["display_name"]
            ).display_name(job.get("secondary_family")),
        },
        "public": {
            "target_role": job.get("title"),
            "seniority": job.get("seniority"),
            "primary_family": job.get("primary_family"),
            "secondary_family": job.get("secondary_family"),
            "primary_family_display": display.get("primary_family"),
            "secondary_family_display": display.get("secondary_family"),
            "must_have_skills": display.get("must_have") or [],
            "preferred_skills": display.get("preferred") or [],
            "responsibilities": display.get("responsibilities") or [],
            "certifications": display.get("certs") or [],
        },
        "advanced": {
            "hybrid_probability": meta.get("hybrid_probability"),
            "p1": meta.get("p1") or [],
            "p2": meta.get("p2") or [],
            "p3": meta.get("p3") or [],
            "p4": meta.get("p4") or [],
            "raw": meta.get("full_blueprint") or {},
        },
        "blueprint_path": job.get("blueprint_path"),
    }


def public_analysis(blueprint: dict[str, Any]) -> dict[str, Any]:
    from resume_engine.ui.services.family_registry_service import display_name
    job = blueprint.get("job") or {}
    skills = blueprint.get("priority_skills") or blueprint.get("skills") or {}
    return {
        "target_role": job.get("target_title"),
        "seniority": job.get("seniority"),
        "primary_family": job.get("primary_family"),
        "secondary_family": job.get("secondary_family"),
        "primary_family_display": display_name(job.get("primary_family")),
        "secondary_family_display": display_name(job.get("secondary_family")),
        "must_have_skills": skills.get("P1") or skills.get("p1") or [],
        "preferred_skills": skills.get("P2") or skills.get("p2") or [],
        "responsibilities": blueprint.get("responsibilities") or [],
        "certifications": blueprint.get("certifications") or [],
    }


def advanced_analysis(blueprint: dict[str, Any]) -> dict[str, Any]:
    job = blueprint.get("job") or {}
    skills = blueprint.get("priority_skills") or blueprint.get("skills") or {}
    return {
        "hybrid_probability": job.get("hybrid_probability"),
        "p1": skills.get("P1") or skills.get("p1") or [],
        "p2": skills.get("P2") or skills.get("p2") or [],
        "p3": skills.get("P3") or skills.get("p3") or [],
        "p4": skills.get("P4") or skills.get("p4") or [],
        "raw": blueprint,
    }


def load_blueprint(job: dict[str, Any]) -> dict[str, Any] | None:
    from pathlib import Path
    path = job.get("blueprint_path")
    if path and Path(path).exists():
        return json.loads(Path(path).read_text(encoding="utf-8"))
    meta = job.get("metadata") or {}
    return meta.get("full_blueprint")


def extract_upload(filename: str, raw: bytes) -> str:
    from resume_engine.ui.services.jd_service import extract_text_from_upload
    return extract_text_from_upload(filename, raw)


def count_candidates_matched(job: dict[str, Any], candidates: list[dict[str, Any]]) -> int:
    from resume_engine.ui.services.match_service import (
        MATCH_NONE,
        load_family_registry_snapshot,
        match_candidate_to_job,
    )

    reg = load_family_registry_snapshot()
    n = 0
    for cand in candidates:
        result = match_candidate_to_job(cand, job, registry=reg, include_compatible=False)
        if result.match_type != MATCH_NONE and result.is_strict_match:
            n += 1
    return n


def sync_blueprints_into_library() -> int:
    return 0
