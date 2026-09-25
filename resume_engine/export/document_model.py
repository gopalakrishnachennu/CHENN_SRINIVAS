"""Shared document view built from ResumeJSON for DOCX/PDF exporters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from resume_engine.models.resume_schema import ResumeJSON


@dataclass
class ContactHeader:
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    linkedin: str | None = None
    website: str | None = None

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> ContactHeader:
        if not data:
            return cls()
        return cls(
            name=data.get("candidate_name") or data.get("name"),
            email=data.get("email"),
            phone=data.get("phone"),
            location=data.get("location") or data.get("city"),
            linkedin=data.get("linkedin") or data.get("linkedin_url"),
            website=data.get("website") or data.get("portfolio"),
        )

    def contact_line(self) -> str:
        parts = [self.email, self.phone, self.location, self.linkedin, self.website]
        return " | ".join(part for part in parts if part)


@dataclass
class DocumentSection:
    heading: str
    paragraphs: list[str] = field(default_factory=list)
    bullets: list[str] = field(default_factory=list)
    skill_groups: dict[str, list[str]] = field(default_factory=dict)
    jobs: list[dict[str, Any]] = field(default_factory=list)
    projects: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ResumeDocumentView:
    title: str
    contact: ContactHeader
    summary: str
    technical_skills: dict[str, list[str]]
    experience: list[dict[str, Any]]
    projects: list[dict[str, Any]]
    certifications: list[str]
    education: list[str]
    variant_id: str | None = None
    source_blueprint_hash: str | None = None


def build_document_view(
    resume: ResumeJSON | dict[str, Any],
    contact: ContactHeader | dict[str, Any] | None = None,
) -> ResumeDocumentView:
    if isinstance(resume, dict):
        resume = ResumeJSON.model_validate(resume)
    header = (
        contact
        if isinstance(contact, ContactHeader)
        else ContactHeader.from_mapping(contact)
    )

    certifications = list(resume.certifications or [])
    if not certifications and resume.certification_records:
        certifications = [
            record.name
            for record in resume.certification_records
            if record.status == "possessed" or record.candidate_verified
        ]

    experience = []
    for job in resume.experience:
        experience.append(
            {
                "company": job.company,
                "title": job.title,
                "start_date": job.start_date,
                "end_date": job.end_date,
                "bullets": list(job.bullets or []),
            }
        )

    projects = []
    for project in resume.projects:
        projects.append(
            {
                "name": project.name,
                "summary": project.summary,
                "bullets": list(project.bullets or []),
                "technologies": list(project.technologies or []),
            }
        )

    return ResumeDocumentView(
        title=resume.target_title,
        contact=header,
        summary=resume.summary,
        technical_skills=dict(resume.technical_skills or {}),
        experience=experience,
        projects=projects,
        certifications=certifications,
        education=list(resume.education or []),
        variant_id=resume.variant_id,
        source_blueprint_hash=resume.source_blueprint_hash,
    )
