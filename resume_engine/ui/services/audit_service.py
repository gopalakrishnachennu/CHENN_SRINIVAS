"""Operator audit log service (no secrets)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from resume_engine.ui.db import connect_ui_db, ensure_ui_schema

_SECRET_KEYS = {
    "password",
    "api_key",
    "openai_api_key",
    "secret",
    "token",
    "authorization",
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _scrub(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if str(k).lower() in _SECRET_KEYS or "password" in str(k).lower() or "api_key" in str(k).lower():
                out[k] = "[REDACTED]"
            else:
                out[k] = _scrub(v)
        return out
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    if isinstance(value, str) and value.startswith("sk-"):
        return "[REDACTED]"
    return value


def record_audit_event(
    *,
    action: str,
    actor: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    old_value: Any = None,
    new_value: Any = None,
    metadata: dict | None = None,
) -> str:
    ensure_ui_schema()
    event_id = str(uuid.uuid4())
    with connect_ui_db() as conn:
        conn.execute(
            """
            INSERT INTO audit_events(
              event_id, timestamp, actor, action, entity_type, entity_id,
              old_value, new_value, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                _now(),
                actor,
                action,
                entity_type,
                entity_id,
                json.dumps(_scrub(old_value), default=str) if old_value is not None else None,
                json.dumps(_scrub(new_value), default=str) if new_value is not None else None,
                json.dumps(_scrub(metadata or {}), default=str),
            ),
        )
        conn.commit()
    return event_id


def list_audit_events(*, limit: int = 200, action: str | None = None) -> list[dict]:
    ensure_ui_schema()
    with connect_ui_db() as conn:
        if action:
            rows = conn.execute(
                """
                SELECT * FROM audit_events
                WHERE action = ?
                ORDER BY id DESC LIMIT ?
                """,
                (action, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM audit_events ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]
