"""Prompt version manager."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from resume_engine.ui.db import connect_ui_db, ensure_ui_schema
from resume_engine.ui.services.audit_service import record_audit_event

DEFAULT_PROMPTS = {
    "phase1_extraction": "Phase 1 JD extraction prompt (managed via UI versions).",
    "resume_generation": "Resume generation prompt (managed via UI versions).",
    "targeted_repair": "Targeted repair prompt (managed via UI versions).",
    "laya_validator": "Laya validator configuration notes.",
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def ensure_defaults(actor: str | None = "system") -> None:
    ensure_ui_schema()
    with connect_ui_db() as conn:
        for prompt_id, content in DEFAULT_PROMPTS.items():
            row = conn.execute(
                "SELECT 1 FROM prompt_versions WHERE prompt_id = ? LIMIT 1",
                (prompt_id,),
            ).fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO prompt_versions(prompt_id, version, status, content, actor, created_at)
                    VALUES (?, 1, 'ACTIVE', ?, ?, ?)
                    """,
                    (prompt_id, content, actor, _now()),
                )
        conn.commit()


def list_prompts() -> list[dict[str, Any]]:
    ensure_defaults()
    with connect_ui_db() as conn:
        rows = conn.execute(
            """
            SELECT prompt_id,
                   MAX(version) AS latest_version,
                   SUM(CASE WHEN status = 'ACTIVE' THEN 1 ELSE 0 END) AS active_count
            FROM prompt_versions
            GROUP BY prompt_id
            ORDER BY prompt_id
            """
        ).fetchall()
    return [dict(r) for r in rows]


def list_versions(prompt_id: str) -> list[dict[str, Any]]:
    ensure_defaults()
    with connect_ui_db() as conn:
        rows = conn.execute(
            """
            SELECT id, prompt_id, version, status, actor, created_at,
                   substr(content, 1, 120) AS preview
            FROM prompt_versions WHERE prompt_id = ?
            ORDER BY version DESC
            """,
            (prompt_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_version(prompt_id: str, version: int) -> dict[str, Any]:
    ensure_ui_schema()
    with connect_ui_db() as conn:
        row = conn.execute(
            "SELECT * FROM prompt_versions WHERE prompt_id = ? AND version = ?",
            (prompt_id, version),
        ).fetchone()
    if row is None:
        raise KeyError(f"{prompt_id}@{version}")
    return dict(row)


def create_version(prompt_id: str, content: str, *, actor: str | None = None, activate: bool = False) -> dict[str, Any]:
    ensure_defaults()
    with connect_ui_db() as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(version), 0) AS v FROM prompt_versions WHERE prompt_id = ?",
            (prompt_id,),
        ).fetchone()
        version = int(row["v"]) + 1
        status = "DRAFT"
        conn.execute(
            """
            INSERT INTO prompt_versions(prompt_id, version, status, content, actor, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (prompt_id, version, status, content, actor, _now()),
        )
        conn.commit()
    record_audit_event(
        action="prompt.create_version",
        actor=actor,
        entity_type="prompt",
        entity_id=prompt_id,
        metadata={"version": version},
    )
    if activate:
        return activate_version(prompt_id, version, actor=actor)
    return get_version(prompt_id, version)


def activate_version(prompt_id: str, version: int, *, actor: str | None = None) -> dict[str, Any]:
    ensure_ui_schema()
    with connect_ui_db() as conn:
        conn.execute(
            "UPDATE prompt_versions SET status = 'ARCHIVED' WHERE prompt_id = ? AND status = 'ACTIVE'",
            (prompt_id,),
        )
        conn.execute(
            "UPDATE prompt_versions SET status = 'ACTIVE' WHERE prompt_id = ? AND version = ?",
            (prompt_id, version),
        )
        conn.commit()
    record_audit_event(
        action="prompt.activate",
        actor=actor,
        entity_type="prompt",
        entity_id=prompt_id,
        metadata={"version": version},
    )
    return get_version(prompt_id, version)


def rollback_prompt(prompt_id: str, version: int, *, actor: str | None = None) -> dict[str, Any]:
    return activate_version(prompt_id, version, actor=actor)
