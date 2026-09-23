"""Validation center views over stored validation reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from resume_engine.config.settings import PROJECT_ROOT, RUNS_STORAGE_DIR


def list_validation_reports(limit: int = 100) -> list[dict[str, Any]]:
    if not RUNS_STORAGE_DIR.exists():
        return []
    files = sorted(RUNS_STORAGE_DIR.glob("*/*/reports/*/*/final_validation.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    files += sorted(RUNS_STORAGE_DIR.glob("*/*/reports/*/*/after_repair_validation.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    seen = set()
    out = []
    for path in files:
        if path in seen:
            continue
        seen.add(path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
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
            "action": data.get("action"),
            "optimization_score": data.get("optimization_score"),
            "mtime": path.stat().st_mtime,
        })
        if len(out) >= limit:
            break
    return out


def load_validation_report(rel: str) -> dict[str, Any]:
    path = Path(rel)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path = path.resolve()
    path.relative_to(RUNS_STORAGE_DIR.resolve())
    return json.loads(path.read_text(encoding="utf-8"))


def summarize_validators(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in report.get("validator_results") or []:
        rows.append({
            "name": item.get("name"),
            "passed": item.get("passed"),
            "score": item.get("score"),
            "status": "PASS" if item.get("passed") else "FAIL",
            "issue_count": len(item.get("issues") or []),
        })
    return rows
