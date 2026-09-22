from resume_engine.models.jd_blueprint import JDBlueprint
from resume_engine.models.resume_schema import ResumeJSON, SkillProvenance
from resume_engine.validation.text_utils import normalize_text


def source_label(source: str) -> str:
    mapping = {
        "jd_direct": "JD_DIRECT",
        "approved_adjacent": "APPROVED_ADJACENT",
        "llm_generated": "LLM_GENERATED",
    }
    return mapping.get(source.lower(), source.upper())


def blueprint_provenance_map(blueprint: JDBlueprint) -> dict[str, SkillProvenance]:
    provenance: dict[str, SkillProvenance] = {}
    for entity in blueprint.entities:
        provenance[normalize_text(entity.name)] = SkillProvenance(
            name=entity.name,
            source=source_label(entity.source),
            priority=entity.priority,
            parent=entity.parent_skill,
        )
    for certification in blueprint.certifications:
        provenance.setdefault(
            normalize_text(certification.name),
            SkillProvenance(name=certification.name, source="JD_DIRECT", priority="certification"),
        )
    return provenance


def generated_skill_names(resume: ResumeJSON) -> list[str]:
    skills: list[str] = []
    for values in resume.technical_skills.values():
        skills.extend(values)
    skills.extend(resume.certifications)
    for project in resume.projects:
        skills.extend(project.technologies)
    return list(dict.fromkeys(skill.strip() for skill in skills if skill.strip()))


def attach_skill_provenance(blueprint: JDBlueprint, resume: ResumeJSON) -> ResumeJSON:
    known = blueprint_provenance_map(blueprint)
    provenance = []
    for skill in generated_skill_names(resume):
        record = known.get(normalize_text(skill))
        if record is None:
            record = SkillProvenance(name=skill, source="LLM_GENERATED")
        provenance.append(record)
    resume.skill_provenance = provenance
    return resume
