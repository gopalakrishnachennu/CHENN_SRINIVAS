"""Blueprint listing/versioning — never silently overwrite history."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from resume_engine.config.settings import PROJECT_ROOT
from resume_engine.ui.db import connect_ui_db, ensure_ui_schema
from resume_engine.ui.services.audit_service import record_audit_event

BLUEPRINT_DIR = PROJECT_ROOT / "resume_engine_data" / "blueprints"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def list_blueprints(limit: int = 100) -> list[dict[str, Any]]:
    if not BLUEPRINT_DIR.exists():
        return []
    out = []
    for path in sorted(BLUEPRINT_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        job = data.get("job") or {}
        out.append({
            "jd_hash": data.get("jd_hash") or path.stem,
            "path": str(path),
            "target_title": job.get("target_title"),
            "primary_family": job.get("primary_family"),
            "secondary_family": job.get("secondary_family"),
            "mtime": path.stat().st_mtime,
        })
    return out


def load_blueprint(jd_hash: str) -> dict[str, Any]:
    path = BLUEPRINT_DIR / f"{jd_hash}.json"
    if not path.exists():
        # try exact path
        cand = Path(jd_hash)
        if cand.exists():
            path = cand
        else:
            raise FileNotFoundError(jd_hash)
    return json.loads(path.read_text(encoding="utf-8"))


def save_new_version(jd_hash: str, payload: dict[str, Any], *, actor: str | None = None, note: str | None = None) -> dict[str, Any]:
    ensure_ui_schema()
    data = deepcopy(payload)
    data["jd_hash"] = jd_hash
    with connect_ui_db() as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(version), 0) AS v FROM blueprint_versions WHERE jd_hash = ?",
            (jd_hash,),
        ).fetchone()
        version = int(row["v"]) + 1
        conn.execute(
            """
            INSERT INTO blueprint_versions(jd_hash, version, payload_json, actor, note, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (jd_hash, version, json.dumps(data), actor, note, _now()),
        )
        conn.commit()
    # Also write working copy for pipeline use (latest)
    BLUEPRINT_DIR.mkdir(parents=True, exist_ok=True)
    path = BLUEPRINT_DIR / f"{jd_hash}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    record_audit_event(
        action="blueprint.save_version",
        actor=actor,
        entity_type="blueprint",
        entity_id=jd_hash,
        metadata={"version": version, "note": note},
    )
    return {"jd_hash": jd_hash, "version": version, "path": str(path)}


def list_versions(jd_hash: str) -> list[dict[str, Any]]:
    ensure_ui_schema()
    with connect_ui_db() as conn:
        rows = conn.execute(
            """
            SELECT id, jd_hash, version, actor, note, created_at
            FROM blueprint_versions WHERE jd_hash = ?
            ORDER BY version DESC
            """,
            (jd_hash,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_version(jd_hash: str, version: int) -> dict[str, Any]:
    ensure_ui_schema()
    with connect_ui_db() as conn:
        row = conn.execute(
            "SELECT * FROM blueprint_versions WHERE jd_hash = ? AND version = ?",
            (jd_hash, version),
        ).fetchone()
    if row is None:
        raise FileNotFoundError(f"{jd_hash}@{version}")
    return {"meta": dict(row), "payload": json.loads(row["payload_json"])}
