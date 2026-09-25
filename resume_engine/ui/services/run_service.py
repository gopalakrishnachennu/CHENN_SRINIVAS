"""Run browsing helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from resume_engine.config.settings import PROJECT_ROOT, RUNS_STORAGE_DIR
from resume_engine.ui.app_helpers import relative_to_project, scan_run_summaries


def list_runs(**filters) -> list[dict[str, Any]]:
    runs = scan_run_summaries(limit=int(filters.get("limit") or 200))
    jd = filters.get("jd")
    run_id = filters.get("run_id")
    status = filters.get("status")
    if jd:
        runs = [r for r in runs if jd.lower() in str(r.get("jd_hash") or "").lower() or jd.lower() in str(r.get("target_title") or "").lower()]
    if run_id:
        runs = [r for r in runs if run_id in str(r.get("run_id") or "")]
    if status == "pass":
        runs = [r for r in runs if (r.get("validated") or 0) > 0]
    if status == "fail":
        runs = [r for r in runs if (r.get("validated") or 0) == 0]
    return runs


def get_run(jd_hash: str, run_id: str) -> dict[str, Any]:
    summary = RUNS_STORAGE_DIR / jd_hash / run_id / "phase2_summary.json"
    if not summary.exists():
        raise FileNotFoundError(f"{jd_hash}/{run_id}")
    data = json.loads(summary.read_text(encoding="utf-8"))
    root = summary.parent
    artifacts = {
        "raw": [relative_to_project(p) for p in sorted((root / "raw").glob("*.json"))] if (root / "raw").exists() else [],
        "repaired": [relative_to_project(p) for p in sorted((root / "repaired").glob("*.json"))] if (root / "repaired").exists() else [],
        "validated": [relative_to_project(p) for p in sorted((root / "validated").glob("*.json"))] if (root / "validated").exists() else [],
        "rejected": [relative_to_project(p) for p in sorted((root / "rejected").glob("*.json"))] if (root / "rejected").exists() else [],
        "exports": [relative_to_project(p) for p in sorted((root / "exports").glob("*"))] if (root / "exports").exists() else [],
        "reports": [relative_to_project(p) for p in sorted((root / "reports").rglob("*.json"))][:100] if (root / "reports").exists() else [],
    }
    source_jd_path = root / "source_jd.txt"
    return {
        "jd_hash": jd_hash,
        "run_id": run_id,
        "summary": data,
        "artifacts": artifacts,
        "source_jd": source_jd_path.read_text(encoding="utf-8") if source_jd_path.is_file() else None,
        "summary_path": relative_to_project(summary),
    }


def load_json_artifact(rel: str) -> dict[str, Any]:
    path = Path(rel)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path = path.resolve()
    root = RUNS_STORAGE_DIR.resolve()
    path.relative_to(root)  # raises if outside
    return json.loads(path.read_text(encoding="utf-8"))
