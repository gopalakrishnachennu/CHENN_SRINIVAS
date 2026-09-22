import re
from difflib import SequenceMatcher

from resume_engine.models.resume_schema import ResumeJSON


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def contains_term(text: str, term: str) -> bool:
    haystack = normalize_text(text)
    needle = normalize_text(term)
    return needle in haystack


def flatten_resume_text(resume: ResumeJSON) -> str:
    parts = [resume.target_title, resume.summary]
    for skills in resume.technical_skills.values():
        parts.extend(skills)
    for item in resume.experience:
        parts.extend([item.company, item.title])
        parts.extend(item.bullets)
    for project in resume.projects:
        parts.extend([project.name, project.summary])
        parts.extend(project.bullets)
        parts.extend(project.technologies)
    parts.extend(resume.certifications)
    return "\n".join(part for part in parts if part)


def flatten_experience_text(resume: ResumeJSON) -> str:
    parts = []
    for item in resume.experience:
        parts.extend([item.title, *item.bullets])
    for project in resume.projects:
        parts.extend([project.summary, *project.bullets])
    return "\n".join(part for part in parts if part)


def all_bullets(resume: ResumeJSON) -> list[tuple[str, str]]:
    bullets: list[tuple[str, str]] = []
    for exp_i, item in enumerate(resume.experience):
        for bullet_i, bullet in enumerate(item.bullets):
            bullets.append((f"experience[{exp_i}].bullets[{bullet_i}]", bullet))
    for project_i, project in enumerate(resume.projects):
        for bullet_i, bullet in enumerate(project.bullets):
            bullets.append((f"projects[{project_i}].bullets[{bullet_i}]", bullet))
    return bullets


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_text(a), normalize_text(b)).ratio()
