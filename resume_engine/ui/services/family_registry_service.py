"""Family Registry service — deterministic job-family classification."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from resume_engine.ui.db import DEFAULT_FAMILIES, connect_ui_db, ensure_ui_schema
from resume_engine.ui.services.audit_service import record_audit_event


def _now() -> str:
    return datetime.now(UTC).isoformat()


def list_families(
    *, include_inactive: bool = False, active_only: bool | None = None,
) -> list[dict[str, Any]]:
    ensure_ui_schema()
    if active_only is False:
        include_inactive = True
    with connect_ui_db() as conn:
        if include_inactive:
            rows = conn.execute(
                "SELECT * FROM family_registry ORDER BY display_name"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM family_registry WHERE status = 'active' ORDER BY display_name"
            ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_family(family_id: str) -> dict[str, Any]:
    ensure_ui_schema()
    with connect_ui_db() as conn:
        row = conn.execute(
            "SELECT * FROM family_registry WHERE family_id = ?", (family_id,)
        ).fetchone()
    if row is None:
        raise KeyError(family_id)
    return _row_to_dict(row)


def family_choices() -> list[tuple[str, str]]:
    """Return (family_id, display_name) pairs for select dropdowns."""
    return [(f["family_id"], f["display_name"]) for f in list_families()]


def _row_to_dict(row) -> dict[str, Any]:
    return {
        "family_id": row["family_id"],
        "display_name": row["display_name"],
        "aliases": json.loads(row["aliases_json"]),
        "compatible": json.loads(row["compatible_json"]),
        "hybrid": json.loads(row["hybrid_json"]),
        "blocked": json.loads(row["blocked_json"]),
        "status": row["status"],
        "updated_at": row["updated_at"],
    }


def update_family(
    family_id: str,
    *,
    display_name: str | None = None,
    aliases: list[str] | None = None,
    compatible: list[str] | None = None,
    hybrid: list[str] | None = None,
    blocked: list[str] | None = None,
    actor: str | None = None,
) -> dict[str, Any]:
    ensure_ui_schema()
    current = get_family(family_id)
    now = _now()
    new_display = display_name or current["display_name"]
    new_aliases = aliases if aliases is not None else current["aliases"]
    new_compatible = compatible if compatible is not None else current["compatible"]
    new_hybrid = hybrid if hybrid is not None else current["hybrid"]
    new_blocked = blocked if blocked is not None else current["blocked"]

    with connect_ui_db() as conn:
        conn.execute(
            """
            UPDATE family_registry SET
              display_name = ?, aliases_json = ?, compatible_json = ?,
              hybrid_json = ?, blocked_json = ?, updated_at = ?
            WHERE family_id = ?
            """,
            (
                new_display,
                json.dumps(new_aliases),
                json.dumps(new_compatible),
                json.dumps(new_hybrid),
                json.dumps(new_blocked),
                now,
                family_id,
            ),
        )
        conn.commit()
    from resume_engine.ui.services import match_service

    match_service.invalidate_all_matches()
    record_audit_event(
        action="family.update",
        actor=actor,
        entity_type="family_registry",
        entity_id=family_id,
    )
    return get_family(family_id)


def resolve_family(name: str | None) -> str | None:
    """Resolve a display name, alias, or family_id to a canonical family_id."""
    if name is None:
        return None
    text = str(name).strip()
    if not text or text.lower() in {"none", "null", "n/a"}:
        return None
    families = list_families(include_inactive=True)
    lower = text.lower()
    for fam in families:
        if fam["family_id"].lower() == lower:
            return fam["family_id"]
        if fam["display_name"].lower() == lower:
            return fam["family_id"]
        for alias in fam["aliases"]:
            if alias.lower() == lower:
                return fam["family_id"]
    return None


# Aliases used by candidate_service
resolve_family_id = resolve_family


def display_name(family_id: str | None) -> str:
    """Return display name for a family_id, or the raw value if unknown."""
    if not family_id:
        return ""
    try:
        fam = get_family(family_id)
        return fam["display_name"]
    except KeyError:
        return family_id


def reset_to_defaults(*, actor: str | None = None) -> int:
    """Re-seed from DEFAULT_FAMILIES. Returns count seeded."""
    ensure_ui_schema()
    count = 0
    now = _now()
    with connect_ui_db() as conn:
        for fam in DEFAULT_FAMILIES:
            conn.execute(
                """
                INSERT INTO family_registry(
                  family_id, display_name, aliases_json, compatible_json,
                  hybrid_json, blocked_json, status, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'active', ?)
                ON CONFLICT(family_id) DO UPDATE SET
                  display_name=excluded.display_name,
                  aliases_json=excluded.aliases_json,
                  compatible_json=excluded.compatible_json,
                  hybrid_json=excluded.hybrid_json,
                  blocked_json=excluded.blocked_json,
                  updated_at=excluded.updated_at
                """,
                (
                    fam["family_id"],
                    fam["display_name"],
                    json.dumps(fam["aliases"]),
                    json.dumps(fam["compatible"]),
                    json.dumps(fam["hybrid"]),
                    json.dumps(fam["blocked"]),
                    now,
                ),
            )
            count += 1
        conn.commit()
    record_audit_event(action="family.reset_defaults", actor=actor, entity_type="family_registry")
    return count

def family_options() -> list[tuple[str, str]]:
    return family_choices()


def list_families_compat(*, active_only: bool = True, include_inactive: bool = False) -> list:
    """Bridge active_only / include_inactive callers."""
    if include_inactive or not active_only:
        return list_families(include_inactive=True)
    return list_families(include_inactive=False)
