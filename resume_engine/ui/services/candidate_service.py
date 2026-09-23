"""Candidate profile CRUD with versioning. Generated content never auto-promoted to truth."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from resume_engine.ui.db import connect_ui_db, ensure_ui_schema
from resume_engine.ui.services.audit_service import record_audit_event


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _empty_profile() -> dict[str, Any]:
    return {
        "candidate_name": "",
        "email": "",
        "phone": "",
        "location": "",
        "linkedin": "",
        "website": "",
        "target_background_summary": "",
        "technical_skills": [],
        "experience": [],
        "education": [],
        "projects": [],
        "certifications": [],
    }


def list_profiles(*, include_archived: bool = False) -> list[dict[str, Any]]:
    ensure_ui_schema()
    with connect_ui_db() as conn:
        if include_archived:
            rows = conn.execute("SELECT * FROM candidate_profiles ORDER BY updated_at DESC").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM candidate_profiles WHERE status != 'archived' ORDER BY updated_at DESC"
            ).fetchall()
    out = []
    for row in rows:
        payload = json.loads(row["payload_json"])
        out.append({
            "id": row["id"],
            "name": row["name"],
            "status": row["status"],
            "updated_at": row["updated_at"],
            "created_at": row["created_at"],
            "payload": payload,
        })
    return out


def get_profile(profile_id: str) -> dict[str, Any]:
    ensure_ui_schema()
    with connect_ui_db() as conn:
        row = conn.execute("SELECT * FROM candidate_profiles WHERE id = ?", (profile_id,)).fetchone()
    if row is None:
        raise KeyError(profile_id)
    return {
        "id": row["id"],
        "name": row["name"],
        "status": row["status"],
        "updated_at": row["updated_at"],
        "created_at": row["created_at"],
        "payload": json.loads(row["payload_json"]),
    }


def create_profile(payload: dict[str, Any] | None = None, *, actor: str | None = None) -> dict[str, Any]:
    ensure_ui_schema()
    data = _empty_profile()
    if payload:
        data.update(payload)
    profile_id = str(uuid.uuid4())
    name = data.get("candidate_name") or "Unnamed Candidate"
    now = _now()
    with connect_ui_db() as conn:
        conn.execute(
            """
            INSERT INTO candidate_profiles(id, name, status, payload_json, created_at, updated_at)
            VALUES (?, ?, 'active', ?, ?, ?)
            """,
            (profile_id, name, json.dumps(data), now, now),
        )
        conn.execute(
            """
            INSERT INTO candidate_profile_versions(profile_id, version, payload_json, actor, created_at)
            VALUES (?, 1, ?, ?, ?)
            """,
            (profile_id, json.dumps(data), actor, now),
        )
        conn.commit()
    record_audit_event(action="candidate.create", actor=actor, entity_type="candidate", entity_id=profile_id)
    return get_profile(profile_id)


def update_profile(profile_id: str, payload: dict[str, Any], *, actor: str | None = None) -> dict[str, Any]:
    ensure_ui_schema()
    existing = get_profile(profile_id)
    data = existing["payload"]
    data.update(payload)
    name = data.get("candidate_name") or existing["name"]
    now = _now()
    with connect_ui_db() as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(version), 0) AS v FROM candidate_profile_versions WHERE profile_id = ?",
            (profile_id,),
        ).fetchone()
        version = int(row["v"]) + 1
        conn.execute(
            """
            UPDATE candidate_profiles SET name = ?, payload_json = ?, updated_at = ? WHERE id = ?
            """,
            (name, json.dumps(data), now, profile_id),
        )
        conn.execute(
            """
            INSERT INTO candidate_profile_versions(profile_id, version, payload_json, actor, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (profile_id, version, json.dumps(data), actor, now),
        )
        conn.commit()
    record_audit_event(
        action="candidate.update",
        actor=actor,
        entity_type="candidate",
        entity_id=profile_id,
        metadata={"version": version},
    )
    return get_profile(profile_id)


def duplicate_profile(profile_id: str, *, actor: str | None = None) -> dict[str, Any]:
    src = get_profile(profile_id)
    payload = dict(src["payload"])
    payload["candidate_name"] = f"{payload.get('candidate_name') or src['name']} (copy)"
    return create_profile(payload, actor=actor)


def archive_profile(profile_id: str, *, actor: str | None = None) -> None:
    ensure_ui_schema()
    with connect_ui_db() as conn:
        conn.execute(
            "UPDATE candidate_profiles SET status = 'archived', updated_at = ? WHERE id = ?",
            (_now(), profile_id),
        )
        conn.commit()
    record_audit_event(action="candidate.archive", actor=actor, entity_type="candidate", entity_id=profile_id)


def export_profile_json(profile_id: str) -> dict[str, Any]:
    return get_profile(profile_id)["payload"]


def import_profile_json(payload: dict[str, Any], *, actor: str | None = None) -> dict[str, Any]:
    return create_profile(payload, actor=actor)


def list_versions(profile_id: str) -> list[dict[str, Any]]:
    ensure_ui_schema()
    with connect_ui_db() as conn:
        rows = conn.execute(
            """
            SELECT id, profile_id, version, actor, created_at
            FROM candidate_profile_versions WHERE profile_id = ?
            ORDER BY version DESC
            """,
            (profile_id,),
        ).fetchall()
    return [dict(r) for r in rows]
