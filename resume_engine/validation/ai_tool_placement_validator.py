from resume_engine.models.jd_blueprint import JDBlueprint
from resume_engine.models.resume_schema import ResumeJSON
from resume_engine.models.validation_schema import ValidationIssue, ValidatorResult
from resume_engine.validation.text_utils import contains_term, flatten_experience_text


AI_CATEGORIES = {"ai_tool", "ai_framework"}
AI_NAME_HINTS = {
    "openai",
    "claude",
    "anthropic",
    "langchain",
    "langgraph",
    "mcp",
    "bedrock",
    "vertex ai",
    "mosaic ai",
    "rag",
    "embeddings",
}


def _is_ai_entity(category: str, name: str) -> bool:
    lowered = name.lower()
    return category in AI_CATEGORIES or any(hint in lowered for hint in AI_NAME_HINTS)


def validate_ai_tool_placement(blueprint: JDBlueprint, resume: ResumeJSON) -> ValidatorResult:
    issues: list[ValidationIssue] = []
    skills_text = "\n".join(skill for group in resume.technical_skills.values() for skill in group)
    experience_text = flatten_experience_text(resume)
    summary_text = resume.summary
    details = {}

    for entity in blueprint.entities:
        if not _is_ai_entity(entity.category, entity.name):
            continue

        in_skills = contains_term(skills_text, entity.name)
        in_experience = contains_term(experience_text, entity.name)
        in_summary = contains_term(summary_text, entity.name)
        details[entity.name] = {
            "priority": entity.priority,
            "in_skills": in_skills,
            "in_experience": in_experience,
            "in_summary": in_summary,
        }

        if entity.priority in {"P1", "P2"}:
            if not in_skills:
                issues.append(
                    ValidationIssue(
                        code="FAIL_AI_TOOL_MISSING_SKILLS",
                        severity="error",
                        message=f"{entity.name} is {entity.priority} but missing from technical skills.",
                        location="technical_skills",
                        repair_hint=f"Add {entity.name} to technical skills.",
                        metadata={"skill": entity.name, "priority": entity.priority},
                    )
                )
            if not in_experience:
                issues.append(
                    ValidationIssue(
                        code="FAIL_AI_TOOL_MISSING_RESPONSIBILITY",
                        severity="error",
                        message=f"{entity.name} is {entity.priority} but missing from experience responsibilities.",
                        location="experience_responsibilities",
                        repair_hint=f"Add {entity.name} naturally to a relevant responsibility bullet.",
                        metadata={"skill": entity.name, "priority": entity.priority},
                    )
                )

        if entity.priority == "P1" and not in_summary:
            issues.append(
                ValidationIssue(
                    code="WARN_AI_TOOL_MISSING_SUMMARY",
                    severity="warning",
                    message=f"{entity.name} is P1 and should usually appear in the professional summary.",
                    location="professional_summary",
                    repair_hint=f"Consider adding {entity.name} to the summary if central to the JD.",
                    metadata={"skill": entity.name, "priority": entity.priority},
                )
            )

    error_count = sum(1 for issue in issues if issue.severity == "error")
    warning_count = len(issues) - error_count
    score = max(0.0, 100.0 - error_count * 30 - warning_count * 5)
    return ValidatorResult(
        name="ai_tool_placement_validator",
        passed=error_count == 0,
        score=round(score, 2),
        issues=issues,
        details=details,
    )
