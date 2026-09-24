"""Job library service — wraps Phase 1 analysis into a persistent JD library."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from resume_engine.ui.db import connect_ui_db, ensure_ui_schema
from resume_engine.ui.services.audit_service import record_audit_event
from resume_engine.ui.services.family_registry_service import resolve_family

OVERRIDE_FIELDS = [
    ("city", "City"),
    ("state", "State"),
    ("country", "Country"),
    ("work_mode", "Work Mode"),
    ("remote_scope", "Remote Scope"),
    ("hybrid_days_per_week", "Hybrid Days"),
    ("employment_type", "Employment Type"),
    ("engagement_type", "Engagement Type"),
    ("salary_min", "Salary Min"),
    ("salary_max", "Salary Max"),
    ("salary_currency", "Salary Currency"),
    ("salary_period", "Salary Period"),
    ("sponsorship_status", "Sponsorship"),
    ("authorization_requirement", "Authorization Requirement"),
    ("student_visa_status", "OPT/CPT"),
    ("h1b_status", "H-1B"),
    ("ead_status", "EAD"),
    ("clearance_status", "Clearance Status"),
    ("clearance_level", "Clearance Level"),
    ("minimum_years_experience", "Minimum Years Experience"),
    ("seniority", "Seniority"),
    ("primary_family", "Primary Family"),
    ("secondary_family", "Secondary Family"),
]

REQUIRED_JOB_INTAKE_FIELDS = [
    ("title", "Job Title"),
    ("company", "Company"),
    ("location", "Location"),
    ("job_url", "JD URL"),
    ("jd_text", "Raw JD"),
]


def validate_required_intake(payload: dict[str, Any]) -> list[str]:
    """Return missing fields that block a job from entering the workflow."""
    missing: list[str] = []
    for field, label in REQUIRED_JOB_INTAKE_FIELDS:
        value = payload.get(field)
        if value is None or not str(value).strip():
            missing.append(label)
    return missing


def workflow_review(job: dict[str, Any]) -> dict[str, Any]:
    """Return stored or computed Laya workflow review for a job."""
    intelligence = job.get("job_intelligence") or {}
    required_missing = validate_required_intake(job)
    stored = (
        intelligence.get("laya_workflow_review")
        or (intelligence.get("laya_output") or {}).get("workflow_review")
    )
    if stored and not required_missing:
        return stored
    from resume_engine.ui.services.laya_service import review_job_workflow

    return review_job_workflow(
        job,
        intelligence,
        required_missing=required_missing,
    )


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
                       jd_content_hash, job_url, seniority, source, updated_at, jd_text,
                       country, state, city, work_mode, employment_type, engagement_type,
                       salary_min, salary_max, salary_currency, salary_period,
                       sponsorship_status, authorization_requirement, student_visa_status,
                       clearance_status, minimum_years_experience
                FROM jd_library ORDER BY updated_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, title, company, location, primary_family, secondary_family,
                       status, analysis_status, analysis_version, blueprint_path,
                       jd_content_hash, job_url, seniority, source, updated_at, jd_text,
                       country, state, city, work_mode, employment_type, engagement_type,
                       salary_min, salary_max, salary_currency, salary_period,
                       sponsorship_status, authorization_requirement, student_visa_status,
                       clearance_status, minimum_years_experience
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
            "jd_text": row["jd_text"],
            "country": row["country"],
            "state": row["state"],
            "city": row["city"],
            "work_mode": row["work_mode"] or "UNKNOWN",
            "employment_type": row["employment_type"] or "UNKNOWN",
            "engagement_type": row["engagement_type"] or "UNKNOWN",
            "salary_min": row["salary_min"],
            "salary_max": row["salary_max"],
            "salary_currency": row["salary_currency"],
            "salary_period": row["salary_period"] or "UNKNOWN",
            "sponsorship_status": row["sponsorship_status"] or "SPONSORSHIP_NOT_STATED",
            "authorization_requirement": row["authorization_requirement"] or "NONE_STATED",
            "student_visa_status": row["student_visa_status"] or "OPT_CPT_NOT_STATED",
            "clearance_status": row["clearance_status"] or "NOT_STATED",
            "minimum_years_experience": row["minimum_years_experience"],
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
        "job_intelligence": json.loads(row["job_intelligence_json"]) if "job_intelligence_json" in keys and row["job_intelligence_json"] else {},
        "job_intelligence_schema_version": row["job_intelligence_schema_version"] if "job_intelligence_schema_version" in keys else None,
        "country": row["country"] if "country" in keys else None,
        "state": row["state"] if "state" in keys else None,
        "city": row["city"] if "city" in keys else None,
        "work_mode": row["work_mode"] if "work_mode" in keys else "UNKNOWN",
        "employment_type": row["employment_type"] if "employment_type" in keys else "UNKNOWN",
        "engagement_type": row["engagement_type"] if "engagement_type" in keys else "UNKNOWN",
        "salary_min": row["salary_min"] if "salary_min" in keys else None,
        "salary_max": row["salary_max"] if "salary_max" in keys else None,
        "salary_currency": row["salary_currency"] if "salary_currency" in keys else None,
        "salary_period": row["salary_period"] if "salary_period" in keys else "UNKNOWN",
        "sponsorship_status": row["sponsorship_status"] if "sponsorship_status" in keys else "SPONSORSHIP_NOT_STATED",
        "authorization_requirement": row["authorization_requirement"] if "authorization_requirement" in keys else "NONE_STATED",
        "student_visa_status": row["student_visa_status"] if "student_visa_status" in keys else "OPT_CPT_NOT_STATED",
        "clearance_status": row["clearance_status"] if "clearance_status" in keys else "NOT_STATED",
        "minimum_years_experience": row["minimum_years_experience"] if "minimum_years_experience" in keys else None,
    }
    # Effective readiness (validates blueprint file / staleness)
    base["analysis_status"] = get_analysis_status(base)
    return base


def analyze_and_store(
    jd_text: str,
    *,
    title: str | None = None,
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
    title = job_data.get("target_title") or title or "Untitled Role"
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

    _persist_job_intelligence(
        job_id,
        jd_text=jd_text,
        company=company,
        location=location,
        source=source,
        job_url=job_url,
        title=title,
        blueprint=blueprint,
    )

    record_audit_event(
        action="job.analyze_store",
        actor=actor,
        entity_type="jd_library",
        entity_id=job_id,
        metadata={"jd_hash": jd_hash, "title": title},
    )
    return get_job(job_id)


def create_draft(
    jd_text: str,
    *,
    title: str | None = None,
    company: str | None = None,
    location: str | None = None,
    job_url: str | None = None,
    source: str = "manual",
    actor: str | None = None,
    allow_duplicate: bool = False,
) -> dict[str, Any]:
    """Save a manually pasted JD without running model analysis."""
    from resume_engine.ui.services.blueprint_lifecycle import ANALYSIS_NEEDS, jd_content_hash

    if not allow_duplicate:
        existing = find_duplicate_job(jd_text=jd_text, job_url=job_url)
        if existing is not None:
            return existing

    job_id = str(uuid.uuid4())
    now = _now()
    ensure_ui_schema()
    fallback_title = title or "Untitled Role"
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
                job_id, jd_content_hash(jd_text), fallback_title, company, location,
                job_url, source, None, None, None, "active", None, jd_text,
                json.dumps({"display": {}, "full_blueprint": {}}), now, now,
                ANALYSIS_NEEDS, 0, None,
            ),
        )
        conn.commit()
    _persist_job_intelligence(
        job_id,
        jd_text=jd_text,
        company=company,
        location=location,
        source=source,
        job_url=job_url,
        title=fallback_title,
        blueprint=None,
    )
    record_audit_event(
        action="job.save_draft",
        actor=actor,
        entity_type="jd_library",
        entity_id=job_id,
        metadata={"title": fallback_title},
    )
    return get_job(job_id)


def _persist_job_intelligence(
    job_id: str,
    *,
    jd_text: str,
    company: str | None = None,
    location: str | None = None,
    source: str | None = None,
    job_url: str | None = None,
    title: str | None = None,
    blueprint: dict[str, Any] | None = None,
    update_role_fields: bool = True,
) -> dict[str, Any]:
    from resume_engine.jd_intelligence.job_analyzer import analyze_text, filter_columns

    intelligence = analyze_text(
        jd_text,
        job_id=job_id,
        company=company,
        location=location,
        source=source,
        job_url=job_url,
        title=title,
        blueprint=blueprint,
    )
    cols = filter_columns(intelligence)
    with connect_ui_db() as conn:
        current = conn.execute(
            "SELECT analysis_version FROM jd_library WHERE id = ?", (job_id,)
        ).fetchone()
        version = int(current["analysis_version"] or 0) if current else 0
        if update_role_fields:
            conn.execute(
                """
                UPDATE jd_library SET
                  job_intelligence_json=?,
                  job_intelligence_schema_version=?,
                  country=?, state=?, city=?,
                  work_mode=?, employment_type=?, engagement_type=?,
                  salary_min=?, salary_max=?, salary_currency=?, salary_period=?,
                  sponsorship_status=?, authorization_requirement=?, student_visa_status=?,
                  clearance_status=?, minimum_years_experience=?,
                  seniority=?, primary_family=?, secondary_family=?
                WHERE id=?
                """,
                (
                    json.dumps(intelligence, sort_keys=True),
                    cols["job_intelligence_schema_version"],
                    cols["country"], cols["state"], cols["city"],
                    cols["work_mode"], cols["employment_type"], cols["engagement_type"],
                    cols["salary_min"], cols["salary_max"], cols["salary_currency"],
                    cols["salary_period"], cols["sponsorship_status"],
                    cols["authorization_requirement"], cols["student_visa_status"],
                    cols["clearance_status"], cols["minimum_years_experience"],
                    cols["seniority"], cols["primary_family"], cols["secondary_family"],
                    job_id,
                ),
            )
        else:
            conn.execute(
                """
                UPDATE jd_library SET
                  job_intelligence_json=?,
                  job_intelligence_schema_version=?,
                  country=?, state=?, city=?,
                  work_mode=?, employment_type=?, engagement_type=?,
                  salary_min=?, salary_max=?, salary_currency=?, salary_period=?,
                  sponsorship_status=?, authorization_requirement=?, student_visa_status=?,
                  clearance_status=?, minimum_years_experience=?
                WHERE id=?
                """,
                (
                    json.dumps(intelligence, sort_keys=True),
                    cols["job_intelligence_schema_version"],
                    cols["country"], cols["state"], cols["city"],
                    cols["work_mode"], cols["employment_type"], cols["engagement_type"],
                    cols["salary_min"], cols["salary_max"], cols["salary_currency"],
                    cols["salary_period"], cols["sponsorship_status"],
                    cols["authorization_requirement"], cols["student_visa_status"],
                    cols["clearance_status"], cols["minimum_years_experience"],
                    job_id,
                ),
            )
        conn.execute(
            """
            INSERT INTO job_analysis_versions(
              job_id, version, job_intelligence_json, blueprint_json, actor, note, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                version,
                json.dumps(intelligence, sort_keys=True),
                json.dumps(blueprint, sort_keys=True) if blueprint else None,
                None,
                "analysis",
                _now(),
            ),
        )
        conn.commit()
    return intelligence


def persist_job_intelligence_for_job(
    job_id: str,
    *,
    blueprint: dict[str, Any] | None = None,
    update_role_fields: bool = True,
) -> dict[str, Any]:
    job = get_job(job_id)
    return _persist_job_intelligence(
        job_id,
        jd_text=job.get("jd_text") or "",
        company=job.get("company"),
        location=job.get("location"),
        source=job.get("source"),
        job_url=job.get("job_url"),
        title=job.get("title"),
        blueprint=blueprint or load_blueprint(job) or None,
        update_role_fields=update_role_fields,
    )


def _coerce_override_value(raw: str) -> Any:
    value = (raw or "").strip()
    if value == "":
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        pass
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _display_value(value: Any) -> str:
    if isinstance(value, dict) and "value" in value:
        value = value.get("value")
    if isinstance(value, (list, dict)):
        return json.dumps(value, sort_keys=True)
    return "" if value is None else str(value)


def _apply_filter_columns(conn, job_id: str, intelligence: dict[str, Any]) -> None:
    from resume_engine.jd_intelligence.job_analyzer import filter_columns

    cols = filter_columns(intelligence)
    conn.execute(
        """
        UPDATE jd_library SET
          job_intelligence_json=?,
          job_intelligence_schema_version=?,
          country=?, state=?, city=?,
          work_mode=?, employment_type=?, engagement_type=?,
          salary_min=?, salary_max=?, salary_currency=?, salary_period=?,
          sponsorship_status=?, authorization_requirement=?, student_visa_status=?,
          clearance_status=?, minimum_years_experience=?,
          seniority=?, primary_family=?, secondary_family=?,
          updated_at=?
        WHERE id=?
        """,
        (
            json.dumps(intelligence, sort_keys=True),
            cols["job_intelligence_schema_version"],
            cols["country"], cols["state"], cols["city"],
            cols["work_mode"], cols["employment_type"], cols["engagement_type"],
            cols["salary_min"], cols["salary_max"], cols["salary_currency"],
            cols["salary_period"], cols["sponsorship_status"],
            cols["authorization_requirement"], cols["student_visa_status"],
            cols["clearance_status"], cols["minimum_years_experience"],
            cols["seniority"], cols["primary_family"], cols["secondary_family"],
            _now(),
            job_id,
        ),
    )


def apply_manual_override(
    job_id: str,
    *,
    field_name: str,
    new_value_raw: str,
    reason: str | None = None,
    actor: str | None = None,
) -> dict[str, Any]:
    """Apply an admin override to the current intelligence JSON and record history."""
    from resume_engine.jd_intelligence.schema import (
        SOURCE_MANUAL,
        STATUS_MANUAL_OVERRIDE,
    )
    from resume_engine.jd_intelligence.schema import field as intelligence_field

    allowed = {name for name, _label in OVERRIDE_FIELDS}
    if field_name not in allowed:
        raise ValueError(f"Unsupported override field: {field_name}")
    job = get_job(job_id)
    intelligence = dict(job.get("job_intelligence") or {})
    if not intelligence:
        intelligence = persist_job_intelligence_for_job(job_id)

    new_value = _coerce_override_value(new_value_raw)
    old_value = intelligence.get(field_name)
    evidence = f"Manual override: {reason}" if reason else "Manual override"
    if isinstance(old_value, dict) and "value" in old_value:
        intelligence[field_name] = intelligence_field(
            new_value,
            status=STATUS_MANUAL_OVERRIDE,
            source=SOURCE_MANUAL,
            evidence=evidence,
            manual_override=True,
        )
    else:
        intelligence[field_name] = new_value
    override = {
        "field_name": field_name,
        "old_value": _display_value(old_value),
        "new_value": _display_value(new_value),
        "actor": actor,
        "timestamp": _now(),
        "reason": reason,
        "analysis_version": job.get("analysis_version") or 0,
    }
    overrides = list(intelligence.get("manual_overrides") or [])
    overrides.append(override)
    intelligence["manual_overrides"] = overrides

    with connect_ui_db() as conn:
        _apply_filter_columns(conn, job_id, intelligence)
        conn.execute(
            """
            INSERT INTO job_manual_overrides(
              job_id, field_name, old_value, new_value, actor, reason,
              analysis_version, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                field_name,
                override["old_value"],
                override["new_value"],
                actor,
                reason,
                override["analysis_version"],
                override["timestamp"],
            ),
        )
        conn.execute(
            """
            INSERT INTO job_analysis_versions(
              job_id, version, job_intelligence_json, blueprint_json, actor, note, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                int(job.get("analysis_version") or 0),
                json.dumps(intelligence, sort_keys=True),
                None,
                actor,
                f"manual override: {field_name}",
                override["timestamp"],
            ),
        )
        conn.commit()
    record_audit_event(
        action="job.manual_override",
        actor=actor,
        entity_type="jd_library",
        entity_id=job_id,
        metadata=override,
    )
    return get_job(job_id)


def list_manual_overrides(job_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
    ensure_ui_schema()
    with connect_ui_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM job_manual_overrides
            WHERE job_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (job_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def list_analysis_versions(job_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
    ensure_ui_schema()
    with connect_ui_db() as conn:
        rows = conn.execute(
            """
            SELECT id, job_id, version, actor, note, created_at, job_intelligence_json
            FROM job_analysis_versions
            WHERE job_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (job_id, limit),
        ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        try:
            payload = json.loads(item.pop("job_intelligence_json") or "{}")
        except json.JSONDecodeError:
            payload = {}
        item["schema_version"] = payload.get("schema_version")
        item["quality_flags"] = payload.get("quality_flags") or []
        out.append(item)
    return out


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
    job_url = updates.get("job_url", existing["job_url"])
    seniority = updates.get("seniority", existing["seniority"])
    pf = updates.get("primary_family", existing["primary_family"])
    sf = updates.get("secondary_family", existing["secondary_family"])
    if sf in ("", "none", "null"):
        sf = None
    status = updates.get("status", existing["status"])
    new_jd_text = updates.get("jd_text")
    jd_text_changed = new_jd_text is not None and (new_jd_text or "") != (existing.get("jd_text") or "")
    explicit_role_fields = any(key in updates for key in ("seniority", "primary_family", "secondary_family"))

    with connect_ui_db() as conn:
        if jd_text_changed:
            from resume_engine.ui.services.blueprint_lifecycle import ANALYSIS_NEEDS

            conn.execute(
                """
                UPDATE jd_library SET
                  title=?, company=?, location=?, job_url=?, seniority=?,
                  primary_family=?, secondary_family=?, status=?,
                  jd_text=?, blueprint_path=NULL, analysis_status=?,
                  jd_content_hash=NULL, job_intelligence_json=NULL,
                  job_intelligence_schema_version=NULL, updated_at=?
                WHERE id=?
                """,
                (
                    title, company, location, job_url, seniority, pf, sf, status,
                    new_jd_text, ANALYSIS_NEEDS, now, job_id,
                ),
            )
        else:
            conn.execute(
                """
                UPDATE jd_library SET
                  title=?, company=?, location=?, job_url=?, seniority=?,
                  primary_family=?, secondary_family=?, status=?, updated_at=?
                WHERE id=?
                """,
                (title, company, location, job_url, seniority, pf, sf, status, now, job_id),
            )
        conn.commit()

    persist_job_intelligence_for_job(
        job_id,
        update_role_fields=jd_text_changed or not explicit_role_fields,
    )

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
