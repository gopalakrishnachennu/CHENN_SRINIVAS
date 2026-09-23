from resume_engine.config import thresholds
from resume_engine.models.jd_blueprint import JDBlueprint
from resume_engine.models.resume_schema import ResumeJSON
from resume_engine.models.validation_schema import ValidationIssue, ValidatorResult
from resume_engine.validation.text_utils import (
    contains_term,
    flatten_experience_text,
    flatten_resume_text,
)


def _coverage(required: list[str], text: str) -> tuple[float, list[str]]:
    if not required:
        return 1.0, []
    missing = [item for item in required if not contains_term(text, item)]
    return (len(required) - len(missing)) / len(required), missing


def _placement_text(resume: ResumeJSON, placement: str) -> str:
    if placement == "professional_summary":
        return resume.summary
    if placement == "technical_skills":
        return "\n".join(skill for group in resume.technical_skills.values() for skill in group)
    if placement == "technical_skills_optional":
        return "\n".join(skill for group in resume.technical_skills.values() for skill in group)
    if placement in {"experience_responsibilities", "selected_experience"}:
        return flatten_experience_text(resume)
    return flatten_resume_text(resume)


def validate_coverage(blueprint: JDBlueprint, resume: ResumeJSON) -> ValidatorResult:
    full_text = flatten_resume_text(resume)
    issues: list[ValidationIssue] = []
    details = {}

    thresholds_by_priority = {
        "P1": thresholds.P1_COVERAGE_MIN,
        "P2": thresholds.P2_COVERAGE_MIN,
        "P3": thresholds.P3_COVERAGE_MIN,
    }

    priority_scores = {}
    for priority, min_coverage in thresholds_by_priority.items():
        required = blueprint.priority_skills.get(priority, [])
        coverage, missing = _coverage(required, full_text)
        priority_scores[priority] = coverage
        details[f"{priority}_coverage"] = coverage
        details[f"{priority}_missing"] = missing

        if coverage < min_coverage:
            issues.append(
                ValidationIssue(
                    code=f"FAIL_{priority}_COVERAGE",
                    severity="error" if priority in {"P1", "P2"} else "warning",
                    message=f"{priority} coverage {coverage:.0%} is below required {min_coverage:.0%}.",
                    repair_hint=f"Add coverage for: {', '.join(missing)}",
                    metadata={"missing": missing},
                )
            )

    p4_skills = {skill for skill in blueprint.priority_skills.get("P4", [])}

    for entity in blueprint.entities:
        # P4 / technical_skills_optional means allowed, never required.
        if entity.priority == "P4" or entity.name in p4_skills:
            continue
        for placement in entity.placement:
            if placement == "technical_skills_optional":
                continue
            placement_text = _placement_text(resume, placement)
            if not contains_term(placement_text, entity.name):
                severity = "error" if entity.priority in {"P1", "P2"} else "warning"
                issues.append(
                    ValidationIssue(
                        code="FAIL_MISSING_REQUIRED_PLACEMENT",
                        severity=severity,
                        message=f"{entity.name} is missing required placement: {placement}",
                        location=placement,
                        repair_hint=f"Add '{entity.name}' naturally to {placement}.",
                        metadata={"skill": entity.name, "placement": placement, "priority": entity.priority},
                    )
                )

    score = round(sum(priority_scores.values()) / max(1, len(priority_scores)) * 100, 2)
    passed = not any(issue.severity == "error" for issue in issues)
    return ValidatorResult(
        name="coverage_validator",
        passed=passed,
        score=score,
        issues=issues,
        details=details,
    )
