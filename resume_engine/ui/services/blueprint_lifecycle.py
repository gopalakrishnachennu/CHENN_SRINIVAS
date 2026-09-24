"""JD blueprint lifecycle — never trust a bare blueprint_path without validation."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from resume_engine.ui.db import connect_ui_db, ensure_ui_schema
from resume_engine.ui.services import match_service
from resume_engine.ui.services.audit_service import record_audit_event

ANALYSIS_READY = "READY"
ANALYSIS_NEEDS = "NEEDS_ANALYSIS"
ANALYSIS_ANALYZING = "ANALYZING"
ANALYSIS_FAILED = "FAILED"
ANALYSIS_ARCHIVED = "ARCHIVED"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def jd_content_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:32]


def _blueprint_valid(path: str | None, expected_hash: str | None) -> bool:
    if not path:
        return False
    p = Path(path)
    if not p.exists() or not p.is_file():
        return False
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict) or not data.get("job"):
        return False
    if expected_hash:
        bp_hash = data.get("jd_hash") or ""
        # Accept if content hash recorded on job matches file's jd_hash OR stored hash
        # Stale when job's jd_content_hash differs from what was analyzed
        _ = bp_hash
    return True


def get_analysis_status(job: dict[str, Any]) -> str:
    status = (job.get("status") or "active").lower()
    if status == "archived":
        return ANALYSIS_ARCHIVED
    raw = (job.get("analysis_status") or "").upper()
    if raw in {ANALYSIS_READY, ANALYSIS_NEEDS, ANALYSIS_ANALYZING, ANALYSIS_FAILED}:
        # Verify READY still has a real blueprint
        if raw == ANALYSIS_READY:
            if not _blueprint_valid(job.get("blueprint_path"), job.get("jd_content_hash")):
                return ANALYSIS_NEEDS
            # Stale if content hash changed
            text = job.get("jd_text") or ""
            if job.get("jd_content_hash") and jd_content_hash(text) != job.get("jd_content_hash"):
                return ANALYSIS_NEEDS
        return raw
    # Legacy rows: infer
    if _blueprint_valid(job.get("blueprint_path"), job.get("jd_content_hash")):
        return ANALYSIS_READY
    return ANALYSIS_NEEDS


def _set_job_analysis(
    job_id: str,
    *,
    analysis_status: str,
    blueprint_path: str | None = None,
    jd_hash: str | None = None,
    bump_version: bool = False,
    families: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    ensure_ui_schema()
    now = _now()
    with connect_ui_db() as conn:
        row = conn.execute("SELECT * FROM jd_library WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        version = int(row["analysis_version"] or 0)
        if bump_version:
            version += 1
        meta = json.loads(row["metadata_json"] or "{}")
        if error:
            meta["last_analysis_error"] = error
        else:
            meta.pop("last_analysis_error", None)
        text = row["jd_text"] or ""
        content_hash = jd_content_hash(text) if analysis_status == ANALYSIS_READY else row["jd_content_hash"]
        sets = [
            "analysis_status = ?",
            "analysis_version = ?",
            "updated_at = ?",
            "metadata_json = ?",
        ]
        params: list[Any] = [analysis_status, version, now, json.dumps(meta)]
        if blueprint_path is not None:
            sets.append("blueprint_path = ?")
            params.append(blueprint_path)
        if jd_hash is not None:
            sets.append("jd_hash = ?")
            params.append(jd_hash)
        if analysis_status == ANALYSIS_READY:
            sets.append("jd_content_hash = ?")
            params.append(content_hash)
        if families:
            if families.get("title"):
                sets.append("title = ?")
                params.append(families["title"])
            if families.get("seniority") is not None:
                sets.append("seniority = ?")
                params.append(families["seniority"])
            if families.get("primary_family") is not None:
                sets.append("primary_family = ?")
                params.append(families["primary_family"])
            if families.get("secondary_family") is not None or "secondary_family" in families:
                sets.append("secondary_family = ?")
                params.append(families.get("secondary_family"))
        params.append(job_id)
        conn.execute(f"UPDATE jd_library SET {', '.join(sets)} WHERE id = ?", params)
        conn.commit()


def ensure_job_blueprint(job_id: str, *, actor: str | None = None, force: bool = False) -> dict[str, Any]:
    """Ensure job has a valid READY blueprint; analyze/regenerate as needed.

    Never raises a raw 'blueprint_path' string to the UI — returns structured status.
    """
    from resume_engine.ui.services.family_registry_service import resolve_family
    from resume_engine.ui.services.job_service import get_job

    job = get_job(job_id)
    if (job.get("status") or "").lower() == "archived":
        return {
            "ok": False,
            "job_id": job_id,
            "analysis_status": ANALYSIS_ARCHIVED,
            "reason": "JOB_ARCHIVED",
        }

    status = get_analysis_status(job)
    if status == ANALYSIS_READY and not force:
        return {
            "ok": True,
            "job_id": job_id,
            "analysis_status": ANALYSIS_READY,
            "blueprint_path": job.get("blueprint_path"),
            "jd_hash": job.get("jd_hash"),
            "reused": True,
        }

    jd_text = (job.get("jd_text") or "").strip()
    if not jd_text:
        _set_job_analysis(job_id, analysis_status=ANALYSIS_FAILED, error="empty_jd_text")
        return {
            "ok": False,
            "job_id": job_id,
            "analysis_status": ANALYSIS_FAILED,
            "reason": "JOB_JD_TEXT_MISSING",
        }

    _set_job_analysis(job_id, analysis_status=ANALYSIS_ANALYZING)
    try:
        from resume_engine.ui.services.jd_service import analyze_jd

        result = analyze_jd(jd_text, actor=actor)
        blueprint = result["blueprint"]
        path = result["path"]
        job_block = blueprint.get("job") or {}
        primary = resolve_family(job_block.get("primary_family")) or job_block.get("primary_family")
        secondary = resolve_family(job_block.get("secondary_family"))
        if secondary in {"none", None}:
            secondary = None
        _set_job_analysis(
            job_id,
            analysis_status=ANALYSIS_READY,
            blueprint_path=str(path),
            jd_hash=blueprint.get("jd_hash"),
            bump_version=True,
            families={
                "title": job_block.get("target_title") or job.get("title"),
                "seniority": job_block.get("seniority") or job.get("seniority"),
                "primary_family": primary,
                "secondary_family": secondary,
            },
        )
        match_service.invalidate_matches_for_job(job_id)
        record_audit_event(
            action="job.ensure_blueprint",
            actor=actor,
            entity_type="jd",
            entity_id=job_id,
            metadata={"blueprint_path": str(path), "jd_hash": blueprint.get("jd_hash")},
        )
        return {
            "ok": True,
            "job_id": job_id,
            "analysis_status": ANALYSIS_READY,
            "blueprint_path": str(path),
            "jd_hash": blueprint.get("jd_hash"),
            "reused": False,
        }
    except Exception as exc:  # noqa: BLE001
        _set_job_analysis(job_id, analysis_status=ANALYSIS_FAILED, error=str(exc))
        return {
            "ok": False,
            "job_id": job_id,
            "analysis_status": ANALYSIS_FAILED,
            "reason": "JOB_ANALYSIS_FAILED",
            "error": str(exc),
        }


def mark_job_needs_analysis(job_id: str, *, actor: str | None = None) -> None:
    _set_job_analysis(job_id, analysis_status=ANALYSIS_NEEDS, blueprint_path="")
    match_service.invalidate_matches_for_job(job_id)
    record_audit_event(
        action="job.mark_needs_analysis",
        actor=actor,
        entity_type="jd",
        entity_id=job_id,
    )
