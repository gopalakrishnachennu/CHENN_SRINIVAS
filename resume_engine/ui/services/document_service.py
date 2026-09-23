"""Document template designer defaults — preserve current exporter behavior."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from resume_engine.ui.db import connect_ui_db, ensure_ui_schema
from resume_engine.ui.services.audit_service import record_audit_event

DEFAULT_TEMPLATES = {
    "classic_ats": {
        "name": "Classic ATS",
        "font": "Calibri",
        "body_font_size": 11,
        "heading_font_size": 14,
        "name_font_size": 18,
        "margins_in": 0.7,
        "line_spacing": 1.08,
        "accent_color": "#0f5c4c",
        "bullet_indent": 0.25,
        "section_spacing": 8,
        "page_target": 2,
    },
    "modern_ats": {
        "name": "Modern ATS",
        "font": "Calibri",
        "body_font_size": 10.5,
        "heading_font_size": 13,
        "name_font_size": 18,
        "margins_in": 0.6,
        "line_spacing": 1.05,
        "accent_color": "#1f4e79",
        "bullet_indent": 0.2,
        "section_spacing": 6,
        "page_target": 2,
    },
    "compact_two_page": {
        "name": "Compact Two Page",
        "font": "Calibri",
        "body_font_size": 10,
        "heading_font_size": 12,
        "name_font_size": 16,
        "margins_in": 0.5,
        "line_spacing": 1.0,
        "accent_color": "#333333",
        "bullet_indent": 0.18,
        "section_spacing": 4,
        "page_target": 2,
    },
    "executive": {
        "name": "Executive",
        "font": "Calibri",
        "body_font_size": 11,
        "heading_font_size": 14,
        "name_font_size": 20,
        "margins_in": 0.75,
        "line_spacing": 1.15,
        "accent_color": "#0f5c4c",
        "bullet_indent": 0.25,
        "section_spacing": 10,
        "page_target": 2,
    },
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def ensure_defaults() -> None:
    ensure_ui_schema()
    with connect_ui_db() as conn:
        for tid, payload in DEFAULT_TEMPLATES.items():
            row = conn.execute("SELECT 1 FROM document_templates WHERE id = ?", (tid,)).fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO document_templates(id, name, payload_json, is_default, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (tid, payload["name"], json.dumps(payload), 1 if tid == "classic_ats" else 0, _now(), _now()),
                )
        conn.commit()


def list_templates() -> list[dict[str, Any]]:
    ensure_defaults()
    with connect_ui_db() as conn:
        rows = conn.execute("SELECT * FROM document_templates ORDER BY name").fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["payload"] = json.loads(row["payload_json"])
        out.append(item)
    return out


def save_template(template_id: str, payload: dict[str, Any], *, actor: str | None = None) -> dict[str, Any]:
    ensure_defaults()
    name = payload.get("name") or template_id
    with connect_ui_db() as conn:
        conn.execute(
            """
            INSERT INTO document_templates(id, name, payload_json, is_default, created_at, updated_at)
            VALUES (?, ?, ?, 0, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              name=excluded.name,
              payload_json=excluded.payload_json,
              updated_at=excluded.updated_at
            """,
            (template_id, name, json.dumps(payload), _now(), _now()),
        )
        conn.commit()
    record_audit_event(action="document.save", actor=actor, entity_type="document_template", entity_id=template_id)
    return {"id": template_id, "payload": payload}
