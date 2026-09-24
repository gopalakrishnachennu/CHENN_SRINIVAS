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
    from resume_engine.ui.services.job_service import (
        get_job,
        validate_required_intake,
        workflow_review,
    )

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
    required_missing = validate_required_intake(job)
    if required_missing:
        raise PreflightError(
            "JOB_REQUIRED_INTAKE_MISSING",
            f"Required job intake missing: {', '.join(required_missing)}",
        )
    review = workflow_review(job)
    if review.get("readiness") == "BLOCKED":
        blocked = ", ".join(item["label"] for item in review.get("human_review_queue") or [])
        raise PreflightError(
            "LAYA_WORKFLOW_BLOCKED",
            f"Laya workflow guard blocked resume creation: {blocked or 'review required'}",
        )

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
    variants: int = 1,
    repair: bool = False,
    laya: bool = True,
    export_docx: bool = True,
    export_pdf: bool = True,
    model: str | None = None,
    actor: str | None = None,
) -> dict[str, Any]:
    """Prepare blueprint if needed, preflight, then queue generation."""
    from resume_engine.ui.services.job_service import (
        get_job,
        validate_required_intake,
        workflow_review,
    )

    job = get_job(jd_id)
    required_missing = validate_required_intake(job)
    if required_missing:
        raise PreflightError(
            "JOB_REQUIRED_INTAKE_MISSING",
            f"Required job intake missing: {', '.join(required_missing)}",
        )
    review = workflow_review(job)
    if review.get("readiness") == "BLOCKED":
        blocked = ", ".join(item["label"] for item in review.get("human_review_queue") or [])
        raise PreflightError(
            "LAYA_WORKFLOW_BLOCKED",
            f"Laya workflow guard blocked resume creation: {blocked or 'review required'}",
        )

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
        model=model,
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
    model: str | None = None,
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
        "single_call": vc == 1 and not bool(rep),
        "model": model or get_effective_setting("openai_resume_generation_model") or get_effective_setting("default_openai_model"),
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
    from resume_engine.ui.services import openai_command_service

    status = job.get("status") or "QUEUED"
    stage = (job.get("stage") or "").lower()
    payload = job.get("payload") or {}
    result = job.get("result") or {}
    progress_message = result.get("progress_message") if isinstance(result, dict) else None
    progress_detail = result.get("progress_detail") if isinstance(result, dict) else {}
    created_at = job.get("created_at")
    updated_at = job.get("updated_at")

    def _age_seconds(raw: str | None) -> int | None:
        if not raw:
            return None
        try:
            return max(0, int((datetime.now(UTC) - datetime.fromisoformat(raw)).total_seconds()))
        except ValueError:
            return None

    reached = "candidate"
    if status == "RUNNING":
        if stage in {"queued", "preflight", "load_blueprint"}:
            reached = "jd"
        elif stage in {"strategy", "strategy_ready"}:
            reached = "strategy"
        elif stage == "openai_setup" or stage.startswith("generate_variant") or stage == "regenerate_variant":
            reached = "generate"
        elif stage.startswith("variant_") or stage in {"learning", "diversity"}:
            reached = "validate"
        elif stage == "export":
            reached = "export"
        elif stage == "finalize":
            reached = "export"
        else:
            # Keep older jobs readable when they were created before the
            # pipeline started emitting named progress milestones.
            for legacy_stage, step_key in (
                ("phase2", "jd"),
                ("strateg", "strategy"),
                ("generat", "generate"),
                ("validat", "validate"),
                ("repair", "repair"),
                ("export", "export"),
            ):
                if legacy_stage in stage:
                    reached = step_key
                    break
    exports = result.get("exports") if isinstance(result, dict) else None
    exports = exports if isinstance(exports, list) else []
    variant_results = result.get("variant_results") if isinstance(result, dict) else None
    variant_results = variant_results if isinstance(variant_results, list) else []
    failed_variants = sum(1 for item in variant_results if not item.get("passed"))
    usage = openai_command_service.usage_for_run(job.get("run_id"))
    artifacts_ready = status == "COMPLETED" and bool(exports)
    provider_blocked = any(
        str(row.get("error_class") or "").lower() in {
            "ratelimiterror", "rate_limit", "authenticationerror", "api_connection_error"
        }
        or str(row.get("error_type") or "").lower() in {"insufficient_quota", "invalid_api_key"}
        for row in usage.get("recent", [])
    )
    single_call = bool(payload.get("single_call"))
    repair_skipped = not bool(payload.get("repair")) or single_call
    repair_label = (
        "Repair skipped (single-call mode)"
        if single_call
        else "Repair skipped (disabled)"
        if not payload.get("repair")
        else "Repair completed"
    )
    steps_def = [
        ("candidate", "Candidate loaded"),
        ("match", "Family match confirmed"),
        ("jd", "JD analyzed"),
        ("strategy", "Strategy created"),
        ("generate", "OpenAI resume generation"),
        ("validate", "Validation completed"),
        ("repair", repair_label),
        ("export", "Documents created" if artifacts_ready else "No artifacts created"),
    ]

    if status == "COMPLETED":
        reached = "export"
    order = [k for k, _ in steps_def]
    idx = order.index(reached) if reached in order else 0
    steps = []
    for i, (key, label) in enumerate(steps_def):
        skipped = key == "repair" and repair_skipped
        done = (
            (status == "COMPLETED" and (key != "export" or artifacts_ready))
            or (i < idx and not skipped)
        )
        current = status == "RUNNING" and key == reached
        steps.append({"key": key, "label": label, "done": done, "skipped": skipped, "current": current})
    headline = "Creating resume..."
    if status == "COMPLETED" and artifacts_ready:
        headline = "RESUME READY"
    elif status == "COMPLETED":
        headline = "RUN COMPLETED WITHOUT ARTIFACTS"
    elif status == "FAILED":
        headline = "Something went wrong"
    elif status == "RUNNING":
        headline = next((lab for k, lab in steps_def if k == reached), headline)
    formats = []
    if payload.get("export_docx"):
        formats.append("DOCX")
    if payload.get("export_pdf"):
        formats.append("PDF")
    if not formats:
        formats = ["JSON"]
    elapsed = _age_seconds(created_at)
    updated_age = _age_seconds(updated_at)
    percent = 100 if status == "COMPLETED" else 0 if status == "FAILED" else int(((idx + 1) / len(steps_def)) * 100)
    if status == "QUEUED":
        percent = 5
    current_message = progress_message or {
        "QUEUED": "Queued. Waiting for a generation worker.",
        "RUNNING": "Working through generation pipeline.",
        "COMPLETED": "All requested artifacts are ready.",
        "FAILED": "The run stopped before completion.",
    }.get(status, "Waiting for progress update.")
    if status == "COMPLETED" and not artifacts_ready:
        current_message = (
            "The pipeline finished, but no resume artifact was created. "
            "Review OpenAI Activity and retry after resolving the provider error."
        )
        if provider_blocked:
            current_message = (
                "OpenAI did not return a usable response, so no resume artifact was created. "
                "Check quota, API key, or rate limits, then retry."
            )
    if status == "RUNNING" and reached == "generate" and not usage["totals"].get("requests"):
        current_message = current_message + " Waiting for the first OpenAI response."
    return {
        "status": status,
        "headline": headline,
        "steps": steps,
        "ready": artifacts_ready,
        "artifacts_ready": artifacts_ready,
        "warning": status == "COMPLETED" and not artifacts_ready,
        "provider_blocked": provider_blocked,
        "failed_variants": failed_variants,
        "error": job.get("error"),
        "run_id": job.get("run_id"),
        "job_id": job.get("job_id"),
        "stage": job.get("stage"),
        "percent": percent,
        "current_message": current_message,
        "progress_detail": progress_detail or {},
        "elapsed_seconds": elapsed,
        "updated_seconds_ago": updated_age,
        "model": payload.get("model"),
        "variant_count": payload.get("variant_count"),
        "formats": formats,
        "artifact_label": ", ".join(formats) if artifacts_ready else "None",
        "repair": bool(payload.get("repair")),
        "laya": bool(payload.get("use_laya")),
        "openai_key": openai_command_service.openai_key_status(),
        "openai_usage": usage,
        "payload_summary": {
            "candidate_id": payload.get("candidate_id"),
            "job_id": payload.get("job_id"),
            "match_type": payload.get("match_type"),
            "online_mode": payload.get("online_mode"),
            "single_call": bool(payload.get("single_call")),
        },
        "call_policy": "1 OpenAI call" if payload.get("single_call") else "Multi-step generation",
        "result": {
            "exports": exports,
            "summary_path": result.get("summary_path") if isinstance(result, dict) else None,
            "variants_processed": result.get("variants_processed") if isinstance(result, dict) else None,
        },
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
