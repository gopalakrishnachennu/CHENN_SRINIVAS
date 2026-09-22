import re

from resume_engine.models.jd_blueprint import JDBlueprint
from resume_engine.models.resume_schema import ResumeJSON
from resume_engine.models.validation_schema import ValidationIssue, ValidatorResult
from resume_engine.validation.text_utils import normalize_text


KNOWN_TECH_WORDS = {
    "aws",
    "azure",
    "gcp",
    "databricks",
    "snowflake",
    "terraform",
    "kubernetes",
    "docker",
    "helm",
    "spark",
    "apache spark",
    "pyspark",
    "airflow",
    "python",
    "sql",
    "java",
    "scala",
    "openai",
    "openai api",
    "claude",
    "claude api",
    "anthropic",
    "langchain",
    "langgraph",
    "salesforce",
    "tableau",
    "power bi",
    "dbt",
    "delta lake",
    "unity catalog",
}


def _generated_skill_names(resume: ResumeJSON) -> list[str]:
    skills: list[str] = []
    for values in resume.technical_skills.values():
        skills.extend(values)
    skills.extend(resume.certifications)
    for project in resume.projects:
        skills.extend(project.technologies)
    return list(dict.fromkeys(skill.strip() for skill in skills if skill.strip()))


def _contains_tech_term(text: str, term: str) -> bool:
    pattern = r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])"
    return re.search(pattern, text) is not None


def validate_technology_firewall(blueprint: JDBlueprint, resume: ResumeJSON) -> ValidatorResult:
    allowed = {normalize_text(item) for item in blueprint.generation_contract.allowed_technologies}
    allowed.update({normalize_text(item) for item in blueprint.certifications})
    if "apache spark" in allowed:
        allowed.add("spark")
    if "openai api" in allowed:
        allowed.add("openai")
    if "claude api" in allowed:
        allowed.add("claude")
    if "apache airflow" in allowed:
        allowed.add("airflow")

    issues: list[ValidationIssue] = []
    checked = _generated_skill_names(resume)

    for skill in checked:
        normalized = normalize_text(skill)
        if normalized not in allowed:
            issues.append(
                ValidationIssue(
                    code="FAIL_UNAPPROVED_TECHNOLOGY",
                    severity="error",
                    message=f"Generated technology is not allowed by blueprint: {skill}",
                    location="technical_skills/projects/certifications",
                    repair_hint=f"Remove '{skill}' or replace it with an allowed technology.",
                )
            )

    for provenance in resume.skill_provenance:
        if provenance.source == "LLM_GENERATED":
            issues.append(
                ValidationIssue(
                    code="FAIL_LLM_GENERATED_TECHNOLOGY",
                    severity="error",
                    message=f"Skill provenance is LLM_GENERATED and not approved: {provenance.name}",
                    location="skill_provenance",
                    repair_hint=f"Remove '{provenance.name}' or map it to a JD_DIRECT / APPROVED_ADJACENT skill.",
                    metadata=provenance.model_dump(),
                )
            )

    full_text = normalize_text(resume.summary + "\n" + "\n".join(b for exp in resume.experience for b in exp.bullets))
    for known in KNOWN_TECH_WORDS:
        if _contains_tech_term(full_text, known) and known not in allowed:
            issues.append(
                ValidationIssue(
                    code="FAIL_UNAPPROVED_TECHNOLOGY_IN_TEXT",
                    severity="error",
                    message=f"Resume text mentions unapproved technology: {known}",
                    location="summary/experience",
                    repair_hint=f"Remove '{known}' unless it exists in allowed_technologies.",
                )
            )

    unauthorized_count = len(issues)
    score = 100.0 if unauthorized_count == 0 else 0.0

    return ValidatorResult(
        name="technology_firewall",
        passed=unauthorized_count == 0,
        score=score,
        issues=issues,
        details={"checked_generated_skills": checked, "unauthorized_count": unauthorized_count},
    )
