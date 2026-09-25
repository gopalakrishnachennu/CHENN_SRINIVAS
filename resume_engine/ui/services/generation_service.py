"""Async-ish generation jobs (thread executor). River active mode never enabled."""

from __future__ import annotations

import json
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

from resume_engine.config.settings import PROJECT_ROOT, ensure_storage_dirs
from resume_engine.ui.db import connect_ui_db, ensure_ui_schema
from resume_engine.ui.services.audit_service import record_audit_event
from resume_engine.ui.services.config_service import get_effective_setting

_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ui-gen")
_LOCK = threading.Lock()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def create_generation_job(
    payload: dict[str, Any], *, actor: str | None = None, start_immediately: bool = True
) -> dict[str, Any]:
    ensure_storage_dirs()
    ensure_ui_schema()
    job_id = str(uuid.uuid4())
    run_id = payload.get("run_id") or str(uuid.uuid4())
    payload = dict(payload)
    payload["run_id"] = run_id
    # Force shadow — never honor active
    payload["online_mode"] = "shadow"
    now = _now()
    with connect_ui_db() as conn:
        conn.execute(
            """
            INSERT INTO ui_jobs(job_id, run_id, status, stage, payload_json, created_at, updated_at)
            VALUES (?, ?, 'QUEUED', 'queued', ?, ?, ?)
            """,
            (job_id, run_id, json.dumps(payload), now, now),
        )
        conn.commit()
    record_audit_event(
        action="generation.start",
        actor=actor,
        entity_type="ui_job",
        entity_id=job_id,
        metadata={"run_id": run_id},
    )
    if start_immediately:
        start_generation_job(job_id)
    return get_job(job_id)


def start_generation_job(job_id: str) -> None:
    _EXECUTOR.submit(_run_job, job_id)


def _update(job_id: str, *, status: str | None = None, stage: str | None = None, result: Any = None, error: str | None = None) -> None:
    with connect_ui_db() as conn:
        row = conn.execute("SELECT * FROM ui_jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            return
        conn.execute(
            """
            UPDATE ui_jobs SET
              status = COALESCE(?, status),
              stage = COALESCE(?, stage),
              result_json = COALESCE(?, result_json),
              error = COALESCE(?, error),
              updated_at = ?
            WHERE job_id = ?
            """,
            (
                status,
                stage,
                json.dumps(result) if result is not None else None,
                error,
                _now(),
                job_id,
            ),
        )
        conn.commit()


def _sync_resume_records(payload: dict[str, Any], status: str, result: dict[str, Any] | None = None) -> None:
    resume_id = payload.get("resume_id")
    if not resume_id:
        return
    with connect_ui_db() as conn:
        conn.execute(
            "UPDATE resume_library SET status = ?, result_path = ?, updated_at = ? WHERE id = ?",
            (status.lower(), (result or {}).get("summary_path"), _now(), resume_id),
        )
        conn.execute(
            "UPDATE resume_runs SET status = ?, summary_json = ?, updated_at = ? WHERE run_id = ?",
            (status, json.dumps(result or {}), _now(), payload.get("run_id")),
        )
        conn.commit()


def _run_job(job_id: str) -> None:
    with _LOCK:
        pass
    try:
        job = get_job(job_id)
        if job["status"] == "CANCEL_REQUESTED":
            _update(job_id, status="FAILED", stage="cancelled", error="cancelled")
            return
        _update(job_id, status="RUNNING", stage="preflight", result={"progress_message": "Preparing generation job."})
        payload = job["payload"]
        import os
        os.environ["RESUME_ONLINE_LEARNING_MODE"] = "shadow"

        from resume_engine.pipeline.phase2_pipeline import run_phase2_pipeline

        blueprint = payload.get("blueprint_path")
        if not blueprint and payload.get("generation_mode") != "FACT_DRAFT":
            raise ValueError("blueprint_path required")
        variant_count = int(payload.get("variant_count") or get_effective_setting("default_variant_count"))
        single_call = bool(payload.get("single_call", variant_count == 1 and not payload.get("repair")))
        formats = []
        if payload.get("export_docx", get_effective_setting("default_export_docx")):
            formats.append("docx")
        if payload.get("export_pdf", get_effective_setting("default_export_pdf")):
            formats.append("pdf")

        mode = (payload.get("generation_mode") or "TEMPLATE").upper()
        candidate = payload.get("candidate_profile_path")
        seed = payload.get("resume_seed_path") or str(PROJECT_ROOT / "resume_seed.json")
        if mode in {"CANDIDATE", "FACT_DRAFT"} and not candidate:
            raise ValueError("candidate_profile_path required for candidate resume mode")

        def progress_callback(stage: str, message: str, detail: dict[str, Any] | None = None) -> None:
            _update(
                job_id,
                status="RUNNING",
                stage=stage,
                result={
                    "progress_message": message,
                    "progress_detail": detail or {},
                },
            )

        if payload.get("generation_mode") == "FACT_DRAFT":
            from resume_engine.generation.fact_draft import create_fact_draft

            result = create_fact_draft(
                blueprint_path=blueprint,
                target_title=payload.get("target_title"),
                jd_hash=payload.get("jd_hash"),
                jd_text=payload.get("jd_text"),
                candidate_profile_path=candidate,
                run_id=payload["run_id"],
                formats=formats,
                progress_callback=progress_callback,
            )
            _update(job_id, status="COMPLETED", stage="done", result=result)
            _sync_resume_records(payload, "DRAFT", result)
            return

        result = run_phase2_pipeline(
            blueprint_path=blueprint,
            candidate_profile_path=candidate if mode == "CANDIDATE" else None,
            resume_seed_path=None if mode == "CANDIDATE" else seed,
            variant_limit=variant_count,
            model=payload.get("model") or get_effective_setting("default_openai_model"),
            repair=bool(payload.get("repair", get_effective_setting("repair_default_enabled"))),
            use_laya=bool(payload.get("use_laya", get_effective_setting("laya_default_enabled"))),
            run_id=payload.get("run_id"),
            export_formats=formats or None,
            progress_callback=progress_callback,
            single_call=single_call,
        )
        if not result.get("exports") and not any(v.get("passed") for v in result.get("variant_results") or []):
            failure = next((v for v in result.get("variant_results") or [] if v.get("error_type")), {})
            error = failure.get("error_message") or "No variant passed validation or produced an artifact."
            if "credit_balance_exhausted" in error or "insufficient_quota" in error:
                error = "OpenAI credits are exhausted. Create a fact-only draft now, or add API credits before retrying AI generation."
            _update(job_id, status="FAILED", stage="error", result=result, error=error)
            _sync_resume_records(payload, "FAILED", result)
            return
        _update(job_id, status="COMPLETED", stage="done", result=result)
        _sync_resume_records(payload, "COMPLETED", result)
    except Exception as exc:  # noqa: BLE001
        _update(
            job_id,
            status="FAILED",
            stage="error",
            error=f"{type(exc).__name__}: {exc}",
            result={"traceback": traceback.format_exc()[-2000:]},
        )
        try:
            _sync_resume_records(get_job(job_id)["payload"], "FAILED")
        except Exception:
            pass


def get_job(job_id: str) -> dict[str, Any]:
    ensure_ui_schema()
    with connect_ui_db() as conn:
        row = conn.execute("SELECT * FROM ui_jobs WHERE job_id = ?", (job_id,)).fetchone()
    if row is None:
        raise KeyError(job_id)
    return {
        "job_id": row["job_id"],
        "run_id": row["run_id"],
        "status": row["status"],
        "stage": row["stage"],
        "payload": json.loads(row["payload_json"] or "{}"),
        "result": json.loads(row["result_json"]) if row["result_json"] else None,
        "error": row["error"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_jobs(limit: int = 50) -> list[dict[str, Any]]:
    ensure_ui_schema()
    with connect_ui_db() as conn:
        rows = conn.execute(
            "SELECT job_id, run_id, status, stage, created_at, updated_at, error FROM ui_jobs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def request_cancel(job_id: str, *, actor: str | None = None) -> dict[str, Any]:
    _update(job_id, status="CANCEL_REQUESTED", stage="cancel_requested")
    record_audit_event(action="generation.cancel", actor=actor, entity_type="ui_job", entity_id=job_id)
    return get_job(job_id)
