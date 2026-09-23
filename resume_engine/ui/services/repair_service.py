"""Repair center — inspect repair plans/events; manual edits still validated by engine."""

from __future__ import annotations

import json
from typing import Any

from resume_engine.config.settings import PROJECT_ROOT, RUNS_STORAGE_DIR
from resume_engine.ui.services.audit_service import record_audit_event


def list_repair_events(limit: int = 100) -> list[dict[str, Any]]:
    if not RUNS_STORAGE_DIR.exists():
        return []
    files = sorted(
        RUNS_STORAGE_DIR.glob("*/*/reports/*/*/after_repair_validation.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:limit]
    out = []
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        plan = data.get("repair_plan") or {}
        parts = path.parts
        try:
            idx = parts.index("runs")
            jd_hash, run_id = parts[idx + 1], parts[idx + 2]
        except (ValueError, IndexError):
            jd_hash = run_id = "?"
        out.append({
            "path": str(path.relative_to(PROJECT_ROOT)),
            "jd_hash": jd_hash,
            "run_id": run_id,
            "variant_id": data.get("variant_id"),
            "passed": data.get("passed"),
            "optimization_score": data.get("optimization_score"),
            "issue_count": plan.get("issue_count"),
            "operations": plan.get("operations") or [],
            "failed_bullets": plan.get("failed_bullets") or [],
        })
    return out


def approve_manual_note(rel: str, note: str, *, actor: str | None = None) -> None:
    """Record operator decision only — does not bypass validators."""
    record_audit_event(
        action="repair.note",
        actor=actor,
        entity_type="repair_report",
        entity_id=rel,
        metadata={"note": note},
    )
