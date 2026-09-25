from typing import Literal

from pydantic import BaseModel, Field


class ResumeBullet(BaseModel):
    id: str
    text: str
    technologies: list[str] = Field(default_factory=list)
    responsibility_ids: list[str] = Field(default_factory=list)
    priority_skills: list[str] = Field(default_factory=list)
    family: str | None = None
    provenance: list[str] = Field(default_factory=list)


class ResumeCertification(BaseModel):
    name: str
    status: Literal["possessed", "recommended", "jd_requirement"] = "recommended"
    candidate_verified: bool = False
    requirement: str | None = None


class ResumeExperience(BaseModel):
    company: str
    title: str
    start_date: str = ""
    end_date: str = ""
    bullets: list[str] = Field(default_factory=list)
    bullet_meta: list[ResumeBullet] = Field(default_factory=list)


class ResumeProject(BaseModel):
    name: str
    summary: str
    bullets: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    bullet_meta: list[ResumeBullet] = Field(default_factory=list)


class TechnicalSkillGroup(BaseModel):
    category: str
    skills: list[str]


class OpenAIExperience(BaseModel):
    company: str
    title: str
    bullets: list[str]


class OpenAIProject(BaseModel):
    name: str
    summary: str
    bullets: list[str]
    technologies: list[str]


class SkillProvenance(BaseModel):
    name: str
    source: str
    priority: str | None = None
    parent: str | None = None


class ResumeJSON(BaseModel):
    target_title: str
    summary: str
    technical_skills: dict[str, list[str]] = Field(default_factory=dict)
    experience: list[ResumeExperience] = Field(default_factory=list)
    projects: list[ResumeProject] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    certification_records: list[ResumeCertification] = Field(default_factory=list)
    skill_provenance: list[SkillProvenance] = Field(default_factory=list)
    variant_id: str | None = None
    source_blueprint_hash: str | None = None


class OpenAIResumeJSON(BaseModel):
    target_title: str
    summary: str
    technical_skills: list[TechnicalSkillGroup]
    experience: list[OpenAIExperience]
    projects: list[OpenAIProject]
    certifications: list[str]

    def to_resume_json(self) -> ResumeJSON:
        return ResumeJSON(
            target_title=self.target_title,
            summary=self.summary,
            technical_skills={group.category: group.skills for group in self.technical_skills},
            experience=[ResumeExperience.model_validate(item.model_dump()) for item in self.experience],
            projects=[ResumeProject.model_validate(item.model_dump()) for item in self.projects],
            certifications=self.certifications,
        )
