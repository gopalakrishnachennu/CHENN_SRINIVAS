"""JD workspace service — Phase 1 only; no auto Phase 2."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from resume_engine.config.settings import PROJECT_ROOT
from resume_engine.ui.services.audit_service import record_audit_event

BLUEPRINT_DIR = PROJECT_ROOT / "resume_engine_data" / "blueprints"
DRAFT_DIR = PROJECT_ROOT / "resume_engine" / "storage" / "ui" / "jd_drafts"


def example_jd() -> str:
    sample = PROJECT_ROOT / "sample_jd.txt"
    if sample.exists():
        return sample.read_text(encoding="utf-8")
    return "Senior Cloud Engineer\n\nRequirements: AWS, Terraform, Kubernetes, Python, CI/CD."


def save_draft(text: str, *, name: str = "draft.txt", actor: str | None = None) -> Path:
    DRAFT_DIR.mkdir(parents=True, exist_ok=True)
    path = DRAFT_DIR / name
    path.write_text(text, encoding="utf-8")
    record_audit_event(action="jd.save_draft", actor=actor, entity_type="jd_draft", entity_id=name)
    return path


def list_drafts() -> list[dict[str, Any]]:
    if not DRAFT_DIR.exists():
        return []
    return [
        {"name": p.name, "path": str(p), "mtime": p.stat().st_mtime, "chars": p.stat().st_size}
        for p in sorted(DRAFT_DIR.glob("*.txt"), key=lambda x: x.stat().st_mtime, reverse=True)
    ]


def list_previous_blueprints(limit: int = 50) -> list[dict[str, Any]]:
    if not BLUEPRINT_DIR.exists():
        return []
    items = []
    for path in sorted(BLUEPRINT_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        job = data.get("job") or {}
        items.append({
            "path": str(path),
            "jd_hash": data.get("jd_hash") or path.stem,
            "target_title": job.get("target_title"),
            "primary_family": job.get("primary_family"),
            "mtime": path.stat().st_mtime,
        })
    return items


def analyze_jd(jd_text: str, *, actor: str | None = None) -> dict[str, Any]:
    """Run Phase 1 only. Does not generate resumes."""
    from jd_blueprint_engine import run_phase_1

    blueprint, path = run_phase_1(jd_text)
    record_audit_event(
        action="jd.analyze",
        actor=actor,
        entity_type="blueprint",
        entity_id=blueprint.get("jd_hash"),
        metadata={"path": str(path)},
    )
    return {"blueprint": blueprint, "path": str(path)}


def extract_text_from_upload(filename: str, raw: bytes) -> str:
    name = (filename or "").lower()
    if name.endswith((".txt", ".md")):
        return raw.decode("utf-8", errors="replace")
    if name.endswith(".docx"):
        import re
        import zipfile
        from io import BytesIO
        with zipfile.ZipFile(BytesIO(raw)) as zf:
            xml = zf.read("word/document.xml").decode("utf-8", errors="ignore")
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", xml)).strip()
    if name.endswith(".pdf"):
        # Best-effort plain extraction without heavy deps
        text = raw.decode("latin-1", errors="ignore")
        # crude PDF stream text salvage
        parts = []
        for chunk in text.split("BT"):
            if "ET" in chunk:
                parts.append(chunk.split("ET", 1)[0])
        cleaned = " ".join(parts)
        cleaned = "".join(ch if ch.isprintable() or ch in "\n\t" else " " for ch in cleaned)
        return cleaned.strip() or text[:5000]
    raise ValueError("unsupported file type; use .txt, .docx, or .pdf")
