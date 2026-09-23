"""Export center listing — path-safe downloads via existing path helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from resume_engine.config.settings import EXPORT_STORAGE_DIR, RUNS_STORAGE_DIR
from resume_engine.ui.app_helpers import list_validated_resumes, relative_to_project


def list_exports(limit: int = 200) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    roots = []
    if EXPORT_STORAGE_DIR.exists():
        roots.append(EXPORT_STORAGE_DIR)
    if RUNS_STORAGE_DIR.exists():
        roots.append(RUNS_STORAGE_DIR)
    files = []
    for root in roots:
        files.extend(root.rglob("*.docx"))
        files.extend(root.rglob("*.pdf"))
        files.extend(root.rglob("*.zip"))
    files = sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    for path in files:
        items.append({
            "path": relative_to_project(path),
            "name": path.name,
            "suffix": path.suffix.lower(),
            "mtime": path.stat().st_mtime,
            "size": path.stat().st_size,
        })
    # Also surface validated JSON
    for item in list_validated_resumes(limit=50):
        items.append({
            "path": item["relative"],
            "name": Path(item["relative"]).name,
            "suffix": ".json",
            "mtime": item.get("mtime"),
            "size": None,
            "kind": "validated_resume",
        })
    return items
