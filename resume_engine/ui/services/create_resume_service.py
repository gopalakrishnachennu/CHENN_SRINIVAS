"""Create Resume — preflight + ensure blueprint + generation (shadow River only)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from resume_engine.config.settings import PROJECT_ROOT
from resume_engine.ui.db import connect_ui_db, ensure_ui_schema
from resume_engine.ui.services import match_service
from resume_engine.ui.services.audit_service import record_audit_event
from resume_engine.ui.services.blueprint_lifecycle import (
    ANALYSIS_READY,
    ensure_job_blueprint,
    get_analysis_status,
)
from resume_engine.ui.services.config_service import get_effective_setting
from resume_engine.ui.services.generation_service import create_generation_job
from resume_engine.ui.services.match_service import MATCH_NONE


class PreflightError(PermissionError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _now() -> str:
    return datetime.now(UTC).isoformat()


def preflight_create_resume(candidate_id: str, job_id: str) -> dict[str, Any]:
    """Structured preflight — never starts Phase 2 on failure."""
    from resume_engine.ui.services.candidate_service import get_profile
    from resume_engine.ui.services.job_service import get_job

    try:
        candidate = get_profile(candidate_id)
    except KeyError as exc:
        raise PreflightError("CANDIDATE_NOT_FOUND", "Candidate does not exist") from exc
    if (candidate.get("status") or "").lower() == "archived":
        raise PreflightError("CANDIDATE_ARCHIVED", "Candidate is archived")
    payload = candidate.get("payload") or {}
    if not payload.get("primary_family"):
        raise PreflightError("CANDIDATE_PRIMARY_FAMILY_MISSING", "Candidate primary family required")
    companies = payload.get("companies") or []
    if not companies:
        raise PreflightError("CANDIDATE_COMPANY_HISTORY_MISSING", "Add at least one company")
    for c in companies:
        if not (c.get("company") or "").strip():
            raise PreflightError("CANDIDATE_COMPANY_HISTORY_MISSING", "Company name required")
        if not (c.get("start_date") or "").strip():
            raise PreflightError("CANDIDATE_TIMELINE_INVALID", "Company start date required")

    try:
        job = get_job(job_id)
    except KeyError as exc:
        raise PreflightError("JOB_NOT_FOUND", "Job does not exist") from exc
    if (job.get("status") or "").lower() == "archived":
        raise PreflightError("JOB_ARCHIVED", "Job is archived")

    analysis = get_analysis_status(job)
    if analysis != ANALYSIS_READY:
        raise PreflightError("JOB_BLUEPRINT_NOT_READY", f"Job analysis status is {analysis}")

    bp = job.get("blueprint_path")
    if not bp or not Path(bp).exists():
        raise PreflightError("JOB_BLUEPRINT_NOT_READY", "Blueprint file missing")

    match = match_service.match_candidate_to_job(candidate, job)
    if match.match_type == MATCH_NONE:
        raise PreflightError("FAMILY_NO_LONGER_MATCHES", "Candidate and job no longer match by family")

    return {
        "ok": True,
        "candidate": candidate,
        "job": job,
        "match": match.to_dict(),
        "blueprint_path": bp,
    }


def start_create_resume(
    *,
    candidate_id: str,
    jd_id: str,
    variants: int = 3,
    repair: bool = True,
    laya: bool = True,
    export_docx: bool = True,
    export_pdf: bool = True,
    actor: str | None = None,
) -> dict[str, Any]:
    """Prepare blueprint if needed, preflight, then queue generation."""
    # Ensure blueprint without exposing raw path errors
    ensured = ensure_job_blueprint(jd_id, actor=actor)
    if not ensured.get("ok"):
        raise PreflightError(
            ensured.get("reason") or "JOB_BLUEPRINT_NOT_READY",
            ensured.get("error") or "Preparing job analysis failed",
        )

    check = preflight_create_resume(candidate_id, jd_id)
    match_type = check["match"]["match_type"]
    return start_resume_creation(
        candidate_id=candidate_id,
        job_id=jd_id,
        match_type=match_type,
        variant_count=variants,
        use_laya=laya,
        repair=repair,
        export_docx=export_docx,
        export_pdf=export_pdf,
        actor=actor,
    )


def start_resume_creation(
    *,
    candidate_id: str,
    job_id: str,
    match_type: str,
    variant_count: int | None = None,
    use_laya: bool | None = None,
    repair: bool | None = None,
    export_docx: bool | None = None,
    export_pdf: bool | None = None,
    actor: str | None = None,
) -> dict[str, Any]:
    from resume_engine.ui.services.candidate_service import to_engine_candidate_profile

    # Final hard gate
    check = preflight_create_resume(candidate_id, job_id)
    candidate = check["candidate"]
    job = check["job"]
    blueprint_path = check["blueprint_path"]

    vc = variant_count or int(get_effective_setting("default_variant_count"))
    laya = use_laya if use_laya is not None else get_effective_setting("laya_default_enabled")
    rep = repair if repair is not None else get_effective_setting("repair_default_enabled")
    docx = export_docx if export_docx is not None else get_effective_setting("default_export_docx")
    pdf = export_pdf if export_pdf is not None else get_effective_setting("default_export_pdf")

    resume_id = str(uuid.uuid4())
    now = _now()

    engine_profile = to_engine_candidate_profile(candidate)
    profile_dir = PROJECT_ROOT / "resume_engine" / "storage" / "ui" / "candidate_snapshots"
    profile_dir.mkdir(parents=True, exist_ok=True)
    profile_path = profile_dir / f"{candidate_id}.json"
    profile_path.write_text(json.dumps(engine_profile, indent=2), encoding="utf-8")

    payload = {
        "blueprint_path": blueprint_path,
        "generation_mode": "CANDIDATE",
        "candidate_profile_path": str(profile_path),
        "variant_count": vc,
        "model": get_effective_setting("default_openai_model"),
        "use_laya": bool(laya),
        "repair": bool(rep),
        "export_docx": bool(docx),
        "export_pdf": bool(pdf),
        "resume_id": resume_id,
        "candidate_id": candidate_id,
        "job_id": job_id,
        "match_type": match_type or check["match"]["match_type"],
        "online_mode": "shadow",
    }

    gen_job = create_generation_job(payload, actor=actor)

    ensure_ui_schema()
    with connect_ui_db() as conn:
        conn.execute(
            """
            INSERT INTO resume_library(
              id, candidate_id, job_id, status, provenance, run_id,
              payload_json, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                resume_id,
                candidate_id,
                job_id,
                "generating",
                "GENERATED_ROLE_POSITIONING",
                gen_job.get("run_id"),
                json.dumps(payload),
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO resume_runs(
              run_id, candidate_id, jd_id, jd_hash, job_id, status, match_type,
              summary_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET status=excluded.status, updated_at=excluded.updated_at
            """,
            (
                gen_job.get("run_id") or resume_id,
                candidate_id,
                job_id,
                job.get("jd_hash"),
                gen_job["job_id"],
                "QUEUED",
                payload["match_type"],
                json.dumps({"resume_id": resume_id}),
                now,
                now,
            ),
        )
        conn.commit()

    record_audit_event(
        action="resume.create_start",
        actor=actor,
        entity_type="resume_library",
        entity_id=resume_id,
        metadata={
            "candidate_id": candidate_id,
            "job_id": job_id,
            "match_type": payload["match_type"],
            "job_id_gen": gen_job["job_id"],
        },
    )

    from resume_engine.ui.services.generation_service import get_job as get_gen_job

    return get_gen_job(gen_job["job_id"])


def friendly_progress(job: dict[str, Any]) -> dict[str, Any]:
    status = job.get("status") or "QUEUED"
    stage = (job.get("stage") or "").lower()
    steps_def = [
        ("candidate", "Candidate loaded"),
        ("match", "Family match confirmed"),
        ("jd", "JD analyzed"),
        ("strategy", "Strategy created"),
        ("generate", "Resume generated"),
        ("validate", "Validation completed"),
        ("repair", "Repair completed"),
        ("export", "Documents created"),
    ]
    reached = "candidate"
    if status == "RUNNING":
        for needle, key in [
            ("phase2", "jd"),
            ("strateg", "strategy"),
            ("generat", "generate"),
            ("validat", "validate"),
            ("repair", "repair"),
            ("export", "export"),
        ]:
            if needle in stage:
                reached = key
    if status == "COMPLETED":
        reached = "export"
    order = [k for k, _ in steps_def]
    idx = order.index(reached) if reached in order else 0
    steps = []
    for i, (key, label) in enumerate(steps_def):
        done = status == "COMPLETED" or i < idx
        current = status == "RUNNING" and key == reached
        steps.append({"key": key, "label": label, "done": done or (status == "COMPLETED"), "current": current})
    headline = "Creating resume..."
    if status == "COMPLETED":
        headline = "RESUME READY"
    elif status == "FAILED":
        headline = "Something went wrong"
    elif status == "RUNNING":
        headline = next((lab for k, lab in steps_def if k == reached), headline)
    return {
        "status": status,
        "headline": headline,
        "steps": steps,
        "ready": status == "COMPLETED",
        "error": job.get("error"),
        "run_id": job.get("run_id"),
        "job_id": job.get("job_id"),
    }


def list_resumes(
    *,
    candidate_id: str | None = None,
    job_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    ensure_ui_schema()
    with connect_ui_db() as conn:
        if candidate_id:
            rows = conn.execute(
                "SELECT * FROM resume_library WHERE candidate_id = ? ORDER BY created_at DESC LIMIT ?",
                (candidate_id, limit),
            ).fetchall()
        elif job_id:
            rows = conn.execute(
                "SELECT * FROM resume_library WHERE job_id = ? ORDER BY created_at DESC LIMIT ?",
                (job_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM resume_library ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_resume(resume_id: str) -> dict[str, Any]:
    ensure_ui_schema()
    with connect_ui_db() as conn:
        row = conn.execute(
            "SELECT * FROM resume_library WHERE id = ?", (resume_id,)
        ).fetchone()
    if row is None:
        raise KeyError(resume_id)
    return _row_to_dict(row)


def list_resume_library(limit: int = 100) -> list[dict[str, Any]]:
    items = list_resumes(limit=limit)
    out = []
    for r in items:
        cand_name = r.get("candidate_id")
        job_title = r.get("job_id")
        try:
            from resume_engine.ui.services.candidate_service import get_profile

            cand_name = get_profile(r["candidate_id"])["name"]
        except (KeyError, TypeError, OSError):
            pass
        try:
            from resume_engine.ui.services.job_service import get_job

            job_title = get_job(r["job_id"])["title"]
        except (KeyError, TypeError, OSError):
            pass
        out.append({
            "run_id": r.get("run_id") or r["id"],
            "candidate_id": r["candidate_id"],
            "candidate": cand_name,
            "jd_id": r["job_id"],
            "job_title": job_title,
            "jd_hash": None,
            "status": r["status"],
            "match_type": (r.get("payload") or {}).get("match_type"),
            "created_at": r["created_at"],
            "job_id": (r.get("payload") or {}).get("job_id") or r.get("run_id"),
        })
    return out


def _row_to_dict(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "candidate_id": row["candidate_id"],
        "job_id": row["job_id"],
        "status": row["status"],
        "provenance": row["provenance"],
        "run_id": row["run_id"],
        "variant_index": row["variant_index"],
        "score": row["score"],
        "result_path": row["result_path"],
        "payload": json.loads(row["payload_json"]) if row["payload_json"] else {},
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
