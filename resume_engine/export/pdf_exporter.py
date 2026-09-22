"""PDF exporter for validated ResumeJSON (Phase 3)."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer

from resume_engine.export.document_model import ContactHeader, build_document_view
from resume_engine.models.resume_schema import ResumeJSON


def _styles():
    base = getSampleStyleSheet()
    return {
        "name": ParagraphStyle(
            "ResumeName",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=16,
            alignment=TA_CENTER,
            spaceAfter=4,
        ),
        "title": ParagraphStyle(
            "ResumeTitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=11,
            alignment=TA_CENTER,
            spaceAfter=2,
        ),
        "contact": ParagraphStyle(
            "ResumeContact",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            alignment=TA_CENTER,
            spaceAfter=10,
        ),
        "heading": ParagraphStyle(
            "ResumeHeading",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11,
            spaceBefore=10,
            spaceAfter=4,
            alignment=TA_LEFT,
        ),
        "body": ParagraphStyle(
            "ResumeBody",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            spaceAfter=4,
        ),
        "job": ParagraphStyle(
            "ResumeJob",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            spaceBefore=4,
            spaceAfter=2,
        ),
    }


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def export_resume_pdf(
    resume: ResumeJSON | dict,
    output_path: str | Path,
    *,
    contact: ContactHeader | dict | None = None,
) -> Path:
    view = build_document_view(resume, contact=contact)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(path),
        pagesize=LETTER,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.65 * inch,
    )
    styles = _styles()
    story = []

    name = view.contact.name or view.title
    story.append(Paragraph(_escape(name), styles["name"]))
    if view.contact.name and view.title:
        story.append(Paragraph(_escape(view.title), styles["title"]))
    contact_line = view.contact.contact_line()
    if contact_line:
        story.append(Paragraph(_escape(contact_line), styles["contact"]))
    else:
        story.append(Spacer(1, 6))

    if view.summary:
        story.append(Paragraph("PROFESSIONAL SUMMARY", styles["heading"]))
        story.append(Paragraph(_escape(view.summary), styles["body"]))

    if view.technical_skills:
        story.append(Paragraph("TECHNICAL SKILLS", styles["heading"]))
        for category, skills in view.technical_skills.items():
            line = f"<b>{_escape(category)}:</b> {_escape(', '.join(skills))}"
            story.append(Paragraph(line, styles["body"]))

    if view.experience:
        story.append(Paragraph("EXPERIENCE", styles["heading"]))
        for job in view.experience:
            story.append(
                Paragraph(
                    _escape(f"{job['title']} — {job['company']}"),
                    styles["job"],
                )
            )
            bullets = [
                ListItem(Paragraph(_escape(bullet), styles["body"]), leftIndent=10)
                for bullet in job.get("bullets") or []
            ]
            if bullets:
                story.append(ListFlowable(bullets, bulletType="bullet", leftIndent=15))

    if view.projects:
        story.append(Paragraph("PROJECTS", styles["heading"]))
        for project in view.projects:
            story.append(Paragraph(_escape(project["name"]), styles["job"]))
            if project.get("summary"):
                story.append(Paragraph(_escape(project["summary"]), styles["body"]))
            tech = project.get("technologies") or []
            if tech:
                story.append(
                    Paragraph(
                        f"<b>Technologies:</b> {_escape(', '.join(tech))}",
                        styles["body"],
                    )
                )
            bullets = [
                ListItem(Paragraph(_escape(bullet), styles["body"]), leftIndent=10)
                for bullet in project.get("bullets") or []
            ]
            if bullets:
                story.append(ListFlowable(bullets, bulletType="bullet", leftIndent=15))

    if view.certifications:
        story.append(Paragraph("CERTIFICATIONS", styles["heading"]))
        bullets = [
            ListItem(Paragraph(_escape(cert), styles["body"]), leftIndent=10)
            for cert in view.certifications
        ]
        story.append(ListFlowable(bullets, bulletType="bullet", leftIndent=15))

    doc.build(story)
    return path
