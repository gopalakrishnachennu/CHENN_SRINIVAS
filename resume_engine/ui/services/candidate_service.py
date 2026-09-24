"""Candidate profiles — facts only: contact, families, companies/timeline, optional edu/certs.

Generated titles, skills, bullets, and summaries are NEVER stored as candidate truth.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from resume_engine.ui.db import connect_ui_db, ensure_ui_schema
from resume_engine.ui.services import family_registry_service as families
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
        "primary_family": "",
        "secondary_family": "",
        "companies": [],  # [{company, start_date, end_date}]
        "education": [],
        "certifications": [],
        # Provenance marker — engine-generated content must not land here
        "_schema": "candidate_facts_v2",
    }


def normalize_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Strip legacy generated-content fields; keep verified facts only."""
    data = _empty_profile()
    if not payload:
        return data
    data["candidate_name"] = payload.get("candidate_name") or payload.get("name") or ""
    for key in ("email", "phone", "location", "linkedin", "website"):
        data[key] = payload.get(key) or ""
    primary = families.resolve_family_id(payload.get("primary_family")) or payload.get("primary_family") or ""
    secondary = families.resolve_family_id(payload.get("secondary_family")) or payload.get("secondary_family") or ""
    if secondary in {"none", "null"}:
        secondary = ""
    data["primary_family"] = primary
    data["secondary_family"] = secondary

    companies = payload.get("companies")
    if companies is None and payload.get("experience"):
        # Migrate legacy experience → companies (drop titles/bullets)
        companies = []
        for exp in payload.get("experience") or []:
            if not isinstance(exp, dict):
                continue
            companies.append({
                "company": exp.get("company") or exp.get("employer") or "",
                "start_date": exp.get("start_date") or exp.get("start") or "",
                "end_date": exp.get("end_date") or exp.get("end") or "",
                "provenance": {
                    "company": "VERIFIED_CANDIDATE_INPUT",
                    "start_date": "VERIFIED_CANDIDATE_INPUT",
                    "end_date": "VERIFIED_CANDIDATE_INPUT",
                    "role_title": "NOT_PROVIDED",
                },
            })
    data["companies"] = []
    for c in companies or []:
        if not isinstance(c, dict):
            continue
        data["companies"].append({
            "company": (c.get("company") or "").strip(),
            "start_date": (c.get("start_date") or "").strip(),
            "end_date": (c.get("end_date") or "").strip(),
            "provenance": {
                "company": "VERIFIED_CANDIDATE_INPUT",
                "start_date": "VERIFIED_CANDIDATE_INPUT",
                "end_date": "VERIFIED_CANDIDATE_INPUT",
                "role_title": "NOT_PROVIDED",
            },
        })
    data["education"] = payload.get("education") or []
    certs = payload.get("certifications") or []
    if isinstance(certs, str):
        certs = [p.strip() for p in certs.split(",") if p.strip()]
    data["certifications"] = certs
    return data


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
        payload = normalize_payload(json.loads(row["payload_json"]))
        out.append({
            "id": row["id"],
            "name": row["name"],
            "status": row["status"],
            "updated_at": row["updated_at"],
            "created_at": row["created_at"],
            "payload": payload,
            "primary_family_display": families.display_name(payload.get("primary_family")),
            "secondary_family_display": families.display_name(payload.get("secondary_family")),
            "company_count": len(payload.get("companies") or []),
        })
    return out


def get_profile(profile_id: str) -> dict[str, Any]:
    ensure_ui_schema()
    with connect_ui_db() as conn:
        row = conn.execute("SELECT * FROM candidate_profiles WHERE id = ?", (profile_id,)).fetchone()
    if row is None:
        raise KeyError(profile_id)
    payload = normalize_payload(json.loads(row["payload_json"]))
    return {
        "id": row["id"],
        "name": row["name"],
        "status": row["status"],
        "updated_at": row["updated_at"],
        "created_at": row["created_at"],
        "payload": payload,
        "primary_family_display": families.display_name(payload.get("primary_family")),
        "secondary_family_display": families.display_name(payload.get("secondary_family")),
        "company_count": len(payload.get("companies") or []),
    }


def create_profile(payload: dict[str, Any] | None = None, *, actor: str | None = None) -> dict[str, Any]:
    ensure_ui_schema()
    data = normalize_payload(payload)
    if not data.get("primary_family"):
        raise ValueError("Primary Job Family is required")
    if not families.get_family(data["primary_family"]):
        raise ValueError("Primary Job Family must be selected from the Family Registry")
    if data.get("secondary_family") and not families.get_family(data["secondary_family"]):
        raise ValueError("Secondary Job Family must be selected from the Family Registry")
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
    data = normalize_payload(payload)
    if not data.get("primary_family"):
        raise ValueError("Primary Job Family is required")
    now = _now()
    name = data.get("candidate_name") or "Unnamed Candidate"
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


def to_engine_candidate_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Map facts-only profile to engine candidate shape (companies without invented titles)."""
    p = profile.get("payload") or profile
    experience = []
    for c in p.get("companies") or []:
        experience.append({
            "company": c.get("company"),
            "title": "",  # engine generates positioning
            "start_date": c.get("start_date"),
            "end_date": c.get("end_date"),
            "responsibilities": [],
            "provenance": c.get("provenance") or {
                "company": "VERIFIED_CANDIDATE_INPUT",
                "start_date": "VERIFIED_CANDIDATE_INPUT",
                "end_date": "VERIFIED_CANDIDATE_INPUT",
                "role_title": "GENERATED_ROLE_POSITIONING",
            },
        })
    return {
        "candidate_name": p.get("candidate_name"),
        "email": p.get("email"),
        "phone": p.get("phone"),
        "location": p.get("location"),
        "linkedin": p.get("linkedin"),
        "website": p.get("website"),
        "primary_family": p.get("primary_family"),
        "secondary_family": p.get("secondary_family"),
        "experience": experience,
        "education": p.get("education") or [],
        "certifications": p.get("certifications") or [],
        "technical_skills": [],
        "projects": [],
        "target_background_summary": "",
        "_facts_only": True,
    }


def list_versions(profile_id: str) -> list[dict[str, Any]]:
    ensure_ui_schema()
    with connect_ui_db() as conn:
        rows = conn.execute(
            "SELECT version, actor, created_at FROM candidate_profile_versions WHERE profile_id = ? ORDER BY version",
            (profile_id,),
        ).fetchall()
    return [dict(r) for r in rows]
