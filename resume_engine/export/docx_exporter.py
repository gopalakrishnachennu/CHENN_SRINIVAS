"""DOCX exporter for validated ResumeJSON (Phase 3)."""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt

from resume_engine.export.document_model import (
    ContactHeader,
    ResumeDocumentView,
    build_document_view,
)
from resume_engine.models.resume_schema import ResumeJSON


def _set_run_font(run, *, bold: bool = False, size: int = 11) -> None:
    run.bold = bold
    run.font.size = Pt(size)
    run.font.name = "Calibri"


def export_resume_docx(
    resume: ResumeJSON | dict,
    output_path: str | Path,
    *,
    contact: ContactHeader | dict | None = None,
) -> Path:
    view = build_document_view(resume, contact=contact)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    document = Document()
    for section in document.sections:
        section.top_margin = Inches(0.7)
        section.bottom_margin = Inches(0.7)
        section.left_margin = Inches(0.75)
        section.right_margin = Inches(0.75)

    name = view.contact.name or view.title
    heading = document.add_paragraph()
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = heading.add_run(name)
    _set_run_font(run, bold=True, size=16)

    if view.contact.name and view.title:
        sub = document.add_paragraph()
        sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = sub.add_run(view.title)
        _set_run_font(run, bold=False, size=12)

    contact_line = view.contact.contact_line()
    if contact_line:
        line = document.add_paragraph()
        line.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = line.add_run(contact_line)
        _set_run_font(run, size=9)

    def add_heading(text: str) -> None:
        p = document.add_paragraph()
        run = p.add_run(text.upper())
        _set_run_font(run, bold=True, size=11)
        p.paragraph_format.space_before = Pt(10)
        p.paragraph_format.space_after = Pt(2)

    if view.summary:
        add_heading("Professional Summary")
        p = document.add_paragraph(view.summary)
        for run in p.runs:
            _set_run_font(run, size=10)

    if view.technical_skills:
        add_heading("Technical Skills")
        for category, skills in view.technical_skills.items():
            p = document.add_paragraph()
            label = p.add_run(f"{category}: ")
            _set_run_font(label, bold=True, size=10)
            values = p.add_run(", ".join(skills))
            _set_run_font(values, size=10)

    if view.experience:
        add_heading("Experience")
        for job in view.experience:
            p = document.add_paragraph()
            run = p.add_run(f"{job['title']} — {job['company']}")
            _set_run_font(run, bold=True, size=10)
            for bullet in job.get("bullets") or []:
                bp = document.add_paragraph(bullet, style="List Bullet")
                for run in bp.runs:
                    _set_run_font(run, size=10)

    if view.projects:
        add_heading("Projects")
        for project in view.projects:
            p = document.add_paragraph()
            run = p.add_run(project["name"])
            _set_run_font(run, bold=True, size=10)
            if project.get("summary"):
                sp = document.add_paragraph(project["summary"])
                for run in sp.runs:
                    _set_run_font(run, size=10)
            tech = project.get("technologies") or []
            if tech:
                tp = document.add_paragraph()
                label = tp.add_run("Technologies: ")
                _set_run_font(label, bold=True, size=10)
                values = tp.add_run(", ".join(tech))
                _set_run_font(values, size=10)
            for bullet in project.get("bullets") or []:
                bp = document.add_paragraph(bullet, style="List Bullet")
                for run in bp.runs:
                    _set_run_font(run, size=10)

    if view.certifications:
        add_heading("Certifications")
        for cert in view.certifications:
            bp = document.add_paragraph(cert, style="List Bullet")
            for run in bp.runs:
                _set_run_font(run, size=10)

    document.save(str(path))
    return path


# Keep type alias for callers that import the view.
__all__ = ["export_resume_docx", "ResumeDocumentView"]
