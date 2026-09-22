"""Bullet enrichment: stable IDs, technologies, responsibility mapping, provenance."""

from __future__ import annotations

import re

from resume_engine.models.jd_blueprint import JDBlueprint
from resume_engine.models.resume_schema import (
    ResumeBullet,
    ResumeCertification,
    ResumeJSON,
)
from resume_engine.validation.text_utils import contains_term, normalize_text


STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "that",
    "this",
    "into",
    "using",
    "build",
    "manage",
    "support",
    "develop",
    "create",
    "design",
}


def _keywords(text: str) -> set[str]:
    words = normalize_text(text).replace("/", " ").replace("-", " ").split()
    return {word for word in words if len(word) > 3 and word not in STOPWORDS}


def _extract_technologies(text: str, allowed: list[str]) -> list[str]:
    found = []
    for tech in allowed:
        if contains_term(text, tech):
            found.append(tech)
    return found


def _match_responsibility_ids(text: str, blueprint: JDBlueprint) -> list[tuple[str, float]]:
    bullet_words = _keywords(text)
    matches: list[tuple[str, float]] = []
    for entry in blueprint.responsibility_entries():
        required = _keywords(entry["text"])
        if not required:
            matches.append((entry["id"], 1.0))
            continue
        overlap = len(required & bullet_words) / len(required)
        # Technology boost: shared allowed tech tokens mentioned in responsibility.
        tech_hits = 0
        for tech in blueprint.generation_contract.allowed_technologies:
            if contains_term(entry["text"], tech) and contains_term(text, tech):
                tech_hits += 1
        score = min(1.0, overlap + 0.1 * tech_hits)
        matches.append((entry["id"], score))
    matches.sort(key=lambda item: -item[1])
    return matches


def _priority_skills_in_text(text: str, blueprint: JDBlueprint) -> list[str]:
    found = []
    for priority in ("P1", "P2", "P3", "P4"):
        for skill in blueprint.priority_skills.get(priority, []):
            if contains_term(text, skill):
                found.append(skill)
    return list(dict.fromkeys(found))


def attach_bullet_metadata(blueprint: JDBlueprint, resume: ResumeJSON) -> ResumeJSON:
    """Populate bullet_meta with stable IDs and deterministic mappings."""
    allowed = blueprint.generation_contract.allowed_technologies
    family = blueprint.job.primary_family

    for exp_i, experience in enumerate(resume.experience):
        meta: list[ResumeBullet] = []
        for bullet_i, text in enumerate(experience.bullets):
            ranked = _match_responsibility_ids(text, blueprint)
            responsibility_ids = [rid for rid, score in ranked if score >= 0.45][:3]
            techs = _extract_technologies(text, allowed)
            provenance = []
            for tech in techs:
                entity = next(
                    (item for item in blueprint.entities if normalize_text(item.name) == normalize_text(tech)),
                    None,
                )
                if entity is None:
                    provenance.append("UNKNOWN_STRUCTURED")
                elif entity.source.lower() in {"jd_direct", "approved_adjacent"}:
                    provenance.append(entity.source.upper())
                else:
                    provenance.append(entity.source.upper())
            meta.append(
                ResumeBullet(
                    id=f"EXP_{exp_i}_BULLET_{bullet_i}",
                    text=text,
                    technologies=techs,
                    responsibility_ids=responsibility_ids,
                    priority_skills=_priority_skills_in_text(text, blueprint),
                    family=family,
                    provenance=list(dict.fromkeys(provenance)),
                )
            )
        experience.bullet_meta = meta

    for proj_i, project in enumerate(resume.projects):
        meta = []
        for bullet_i, text in enumerate(project.bullets):
            ranked = _match_responsibility_ids(text, blueprint)
            responsibility_ids = [rid for rid, score in ranked if score >= 0.45][:3]
            techs = list(
                dict.fromkeys(
                    _extract_technologies(text, allowed) + list(project.technologies)
                )
            )
            meta.append(
                ResumeBullet(
                    id=f"PROJECT_{proj_i}_BULLET_{bullet_i}",
                    text=text,
                    technologies=techs,
                    responsibility_ids=responsibility_ids,
                    priority_skills=_priority_skills_in_text(text, blueprint),
                    family=family,
                    provenance=["PROJECT_TECH"],
                )
            )
        project.bullet_meta = meta

    return resume


def apply_certification_policy(
    blueprint: JDBlueprint,
    resume: ResumeJSON,
    generation_mode: str,
    candidate_profile: dict | None = None,
) -> ResumeJSON:
    """
    Template mode: unverified certs are recommended / JD requirement, never possessed.
    Candidate mode: only candidate-verified certs may appear as possessed.
    """
    verified_names = set()
    if candidate_profile:
        for item in candidate_profile.get("certifications", []):
            if isinstance(item, str):
                verified_names.add(normalize_text(item))
            elif isinstance(item, dict) and item.get("verified", True):
                verified_names.add(normalize_text(item.get("name", "")))

    records: list[ResumeCertification] = []
    possessed: list[str] = []

    for cert in blueprint.certifications:
        if generation_mode == "CANDIDATE" and normalize_text(cert.name) in verified_names:
            records.append(
                ResumeCertification(
                    name=cert.name,
                    status="possessed",
                    candidate_verified=True,
                    requirement=cert.requirement,
                )
            )
            possessed.append(cert.name)
        else:
            status = "jd_requirement" if cert.requirement in {"mandatory", "required"} else "recommended"
            records.append(
                ResumeCertification(
                    name=cert.name,
                    status=status,
                    candidate_verified=False,
                    requirement=cert.requirement,
                )
            )

    # Strip LLM-claimed possessed certs that are not verified in candidate mode /
    # never claim possession in template mode.
    if generation_mode == "TEMPLATE":
        resume.certifications = []
    else:
        resume.certifications = [
            name
            for name in resume.certifications
            if normalize_text(name) in verified_names
        ] or possessed

    resume.certification_records = records
    return resume


PROPER_TOOL_RE = re.compile(r"\b([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+){0,2})\b")


def find_unknown_proper_tools(resume: ResumeJSON, allowed: list[str]) -> list[str]:
    """
    Flag capitalized tool-like tokens in bullet text that are not in allowed list
    and not represented in bullet_meta.technologies. Does not invent classification.
    """
    allowed_norm = {normalize_text(item) for item in allowed}
    unknown: list[str] = []
    for experience in resume.experience:
        for bullet in experience.bullets:
            for match in PROPER_TOOL_RE.findall(bullet):
                if normalize_text(match) in allowed_norm:
                    continue
                if match.lower() in {
                    "senior",
                    "engineer",
                    "company",
                    "managed",
                    "built",
                    "developed",
                    "supported",
                    "improved",
                    "applied",
                    "owned",
                    "led",
                    "used",
                    "python",
                }:
                    continue
                # Skip common English Title Case words
                if match in {"AWS", "CI", "CD", "SQL", "API", "ETL", "AI", "ML", "LLM", "RAG"}:
                    if normalize_text(match) not in allowed_norm and match not in allowed:
                        # acronyms still need to be allowed if present
                        if normalize_text(match) not in allowed_norm:
                            unknown.append(match)
                    continue
                if len(match) < 3:
                    continue
                unknown.append(match)
    return list(dict.fromkeys(unknown))
