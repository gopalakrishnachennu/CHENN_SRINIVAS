"""Create Resume service — wizard flow wrapping generation_service."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from resume_engine.ui.db import connect_ui_db, ensure_ui_schema
from resume_engine.ui.services.audit_service import record_audit_event
from resume_engine.ui.services.config_service import get_effective_setting
from resume_engine.ui.services.generation_service import create_generation_job


def _now() -> str:
    return datetime.now(UTC).isoformat()


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
    """Kick off async resume generation for a candidate-job pair."""
    from resume_engine.ui.services.candidate_service import get_profile
    from resume_engine.ui.services.job_service import get_job

    candidate = get_profile(candidate_id)
    job = get_job(job_id)

    blueprint_path = job.get("blueprint_path")
    if not blueprint_path:
        raise ValueError(f"Job {job_id} has no blueprint_path")

    vc = variant_count or int(get_effective_setting("default_variant_count"))
    laya = use_laya if use_laya is not None else get_effective_setting("laya_default_enabled")
    rep = repair if repair is not None else get_effective_setting("repair_default_enabled")
    docx = export_docx if export_docx is not None else get_effective_setting("default_export_docx")
    pdf = export_pdf if export_pdf is not None else get_effective_setting("default_export_pdf")

    resume_id = str(uuid.uuid4())
    now = _now()


    from resume_engine.config.settings import PROJECT_ROOT
    from resume_engine.ui.services.candidate_service import to_engine_candidate_profile

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
        "match_type": match_type,
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
                resume_id, candidate_id, job_id, "generating",
                "GENERATED_ROLE_POSITIONING", gen_job.get("run_id"),
                json.dumps(payload), now, now,
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
            "match_type": match_type,
            "job_id_gen": gen_job["job_id"],
        },
    )

    return {
        "resume_id": resume_id,
        "job_id_gen": gen_job["job_id"],
        "run_id": gen_job.get("run_id"),
        "status": "generating",
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
                "SELECT * FROM resume_library "
                "WHERE candidate_id = ? "
                "ORDER BY created_at DESC LIMIT ?",
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


def update_resume_status(
    resume_id: str,
    status: str,
    *,
    score: float | None = None,
    result_path: str | None = None,
) -> None:
    now = _now()
    with connect_ui_db() as conn:
        conn.execute(
            """
            UPDATE resume_library SET status=?, score=COALESCE(?,score),
              result_path=COALESCE(?,result_path), updated_at=?
            WHERE id=?
            """,
            (status, score, result_path, now, resume_id),
        )
        conn.commit()


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

    from resume_engine.config.settings import PROJECT_ROOT
    from resume_engine.ui.services import candidate_service, match_service
    from resume_engine.ui.services.job_service import get_job
    from resume_engine.ui.services.match_service import MATCH_NONE

    candidate = candidate_service.get_profile(candidate_id)
    job = get_job(jd_id)
    match = match_service.classify_match(
        candidate_primary=candidate["payload"].get("primary_family"),
        candidate_secondary=candidate["payload"].get("secondary_family"),
        jd_primary=job.get("primary_family"),
        jd_secondary=job.get("secondary_family"),
    )
    if match["match_type"] == MATCH_NONE:
        raise PermissionError("Selected job is not a family match for this candidate")

    # Write facts-only snapshot for engine
    engine_profile = candidate_service.to_engine_candidate_profile(candidate)
    profile_dir = PROJECT_ROOT / "resume_engine" / "storage" / "ui" / "candidate_snapshots"
    profile_dir.mkdir(parents=True, exist_ok=True)
    profile_path = profile_dir / f"{candidate_id}.json"
    profile_path.write_text(json.dumps(engine_profile, indent=2), encoding="utf-8")

    result = start_resume_creation(
        candidate_id=candidate_id,
        job_id=jd_id,
        match_type=match["match_type"],
        variant_count=variants,
        use_laya=laya,
        repair=repair,
        export_docx=export_docx,
        export_pdf=export_pdf,
        actor=actor,
    )
    # Also record resume_runs for library UI
    ensure_ui_schema()
    now = _now()
    with connect_ui_db() as conn:
        conn.execute(
            """
            INSERT INTO resume_runs(
              run_id, candidate_id, jd_id, jd_hash, job_id, status, match_type,
              summary_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET status=excluded.status, updated_at=excluded.updated_at
            """,
            (
                result.get("run_id") or result["resume_id"],
                candidate_id,
                jd_id,
                job.get("jd_hash"),
                result.get("job_id_gen"),
                "QUEUED",
                match["match_type"],
                json.dumps({"resume_id": result["resume_id"]}),
                now,
                now,
            ),
        )
        conn.commit()
    # Return generation job shape expected by progress UI
    from resume_engine.ui.services.generation_service import get_job as get_gen_job
    return get_gen_job(result["job_id_gen"])


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
            ("phase2", "jd"), ("strateg", "strategy"), ("generat", "generate"),
            ("validat", "validate"), ("repair", "repair"), ("export", "export"),
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
        steps.append({
            "key": key, "label": label,
            "done": done or (status == "COMPLETED"),
            "current": current,
        })
    headline = "Creating resume..."
    if status == "COMPLETED":
        headline = "RESUME READY"
    elif status == "FAILED":
        headline = "Something went wrong"
    elif status == "RUNNING":
        headline = next(
            (lb for k, lb in steps_def if k == reached),
            headline,
        )
    return {
        "status": status,
        "headline": headline,
        "steps": steps,
        "ready": status == "COMPLETED",
        "error": job.get("error"),
        "run_id": job.get("run_id"),
        "job_id": job.get("job_id"),
    }


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
