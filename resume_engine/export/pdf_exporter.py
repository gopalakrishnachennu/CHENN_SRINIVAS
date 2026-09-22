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
            fontSize=15,
            alignment=TA_CENTER,
            spaceAfter=3,
            leading=18,
        ),
        "title": ParagraphStyle(
            "ResumeTitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=10.5,
            alignment=TA_CENTER,
            spaceAfter=2,
            leading=13,
        ),
        "contact": ParagraphStyle(
            "ResumeContact",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            alignment=TA_CENTER,
            spaceAfter=8,
            leading=11,
        ),
        "heading": ParagraphStyle(
            "ResumeHeading",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=10.5,
            spaceBefore=8,
            spaceAfter=3,
            alignment=TA_LEFT,
            leading=13,
        ),
        "body": ParagraphStyle(
            "ResumeBody",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=12.5,
            spaceAfter=3,
        ),
        "job": ParagraphStyle(
            "ResumeJob",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            spaceBefore=5,
            spaceAfter=2,
            leading=12,
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
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
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
