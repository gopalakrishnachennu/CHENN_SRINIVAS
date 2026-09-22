"""Phase 3 export orchestration — DOCX/PDF from ResumeJSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from resume_engine.config.settings import EXPORT_STORAGE_DIR, ensure_storage_dirs, portable_path
from resume_engine.export.document_model import ContactHeader
from resume_engine.export.docx_exporter import export_resume_docx
from resume_engine.export.pdf_exporter import export_resume_pdf
from resume_engine.models.resume_schema import ResumeJSON


SUPPORTED_FORMATS = ("docx", "pdf")


def load_resume(path: str | Path) -> ResumeJSON:
    with open(path, "r", encoding="utf-8") as f:
        return ResumeJSON.model_validate(json.load(f))


def load_contact(path: str | Path | None) -> ContactHeader:
    if path is None:
        return ContactHeader()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return ContactHeader.from_mapping(data)


def default_export_dir(
    *,
    jd_hash: str | None = None,
    run_id: str | None = None,
) -> Path:
    ensure_storage_dirs()
    root = EXPORT_STORAGE_DIR
    if jd_hash:
        root = root / jd_hash
    if run_id:
        root = root / run_id
    root.mkdir(parents=True, exist_ok=True)
    return root


def export_resume(
    resume: ResumeJSON | dict | str | Path,
    *,
    formats: Iterable[str] = ("docx", "pdf"),
    output_dir: str | Path | None = None,
    basename: str | None = None,
    contact: ContactHeader | dict | str | Path | None = None,
) -> dict[str, Any]:
    """
    Export a resume to one or more document formats.

    Returns portable paths for each written artifact.
    """
    if isinstance(resume, (str, Path)):
        resume_obj = load_resume(resume)
        source_name = Path(resume).stem
    elif isinstance(resume, dict):
        resume_obj = ResumeJSON.model_validate(resume)
        source_name = resume_obj.variant_id or "resume"
    else:
        resume_obj = resume
        source_name = resume_obj.variant_id or "resume"

    if isinstance(contact, (str, Path)):
        contact_obj = load_contact(contact)
    elif isinstance(contact, dict):
        contact_obj = ContactHeader.from_mapping(contact)
    else:
        contact_obj = contact or ContactHeader()

    out_dir = Path(output_dir) if output_dir else default_export_dir(
        jd_hash=resume_obj.source_blueprint_hash,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = basename or source_name or "resume"

    requested = []
    for item in formats:
        fmt = str(item).strip().lower()
        if fmt not in SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported export format: {fmt}. Use {SUPPORTED_FORMATS}.")
        requested.append(fmt)

    artifacts: dict[str, str | None] = {}
    for fmt in requested:
        target = out_dir / f"{stem}.{fmt}"
        if fmt == "docx":
            path = export_resume_docx(resume_obj, target, contact=contact_obj)
        else:
            path = export_resume_pdf(resume_obj, target, contact=contact_obj)
        artifacts[fmt] = portable_path(path)

    return {
        "variant_id": resume_obj.variant_id,
        "jd_hash": resume_obj.source_blueprint_hash,
        "output_dir": portable_path(out_dir),
        "artifacts": artifacts,
        "formats": requested,
    }
