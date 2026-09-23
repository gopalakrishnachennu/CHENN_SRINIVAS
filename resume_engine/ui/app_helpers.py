"""Shared helpers used by UI app and services (avoid circular imports)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from resume_engine.config.settings import PROJECT_ROOT, RUNS_STORAGE_DIR, ensure_storage_dirs


def relative_to_project(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def list_validated_resumes(limit: int = 50) -> list[dict]:
    ensure_storage_dirs()
    root = RUNS_STORAGE_DIR
    if not root.exists():
        return []
    files = sorted(
        (
            path
            for path in root.glob("*/*/validated/*_final.json")
            if "_attempt_" not in path.name
        ),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    items = []
    for path in files[:limit]:
        parts = path.parts
        try:
            runs_idx = parts.index("runs")
            jd_hash = parts[runs_idx + 1]
            run_id = parts[runs_idx + 2]
        except (ValueError, IndexError):
            jd_hash, run_id = "unknown", "unknown"
        items.append(
            {
                "path": path,
                "relative": relative_to_project(path),
                "jd_hash": jd_hash,
                "run_id": run_id,
                "variant_id": path.stem.replace("_final", ""),
                "mtime": path.stat().st_mtime,
            }
        )
    return items


def scan_run_summaries(limit: int = 100) -> list[dict[str, Any]]:
    ensure_storage_dirs()
    if not RUNS_STORAGE_DIR.exists():
        return []
    files = sorted(
        RUNS_STORAGE_DIR.glob("*/*/phase2_summary.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    out: list[dict[str, Any]] = []
    for path in files[:limit]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        parts = path.parts
        try:
            runs_idx = parts.index("runs")
            jd_hash = parts[runs_idx + 1]
            run_id = parts[runs_idx + 2]
        except (ValueError, IndexError):
            jd_hash, run_id = data.get("jd_hash"), data.get("run_id")
        variants = data.get("variant_results") or data.get("variants") or []
        validated = sum(1 for v in variants if isinstance(v, dict) and v.get("passed"))
        scores = [
            float(v.get("score_after_repair") or v.get("score_before_repair"))
            for v in variants
            if isinstance(v, dict)
            and isinstance(v.get("score_after_repair") or v.get("score_before_repair"), (int, float))
        ]
        blueprint = data.get("blueprint") or {}
        job = blueprint.get("job") if isinstance(blueprint, dict) else {}
        out.append(
            {
                "path": relative_to_project(path),
                "jd_hash": jd_hash,
                "run_id": run_id,
                "mtime": path.stat().st_mtime,
                "target_title": (job or {}).get("target_title") if isinstance(job, dict) else None,
                "generation_mode": data.get("generation_mode"),
                "variants": len(variants),
                "validated": validated,
                "average_score": (sum(scores) / len(scores)) if scores else None,
                "status": "COMPLETED",
                "summary": data,
            }
        )
    return out
