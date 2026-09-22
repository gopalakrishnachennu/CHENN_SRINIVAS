from resume_engine.models.jd_blueprint import JDBlueprint
from resume_engine.models.validation_schema import ValidationIssue, ValidatorResult


def validate_blueprint_ready(blueprint: JDBlueprint) -> ValidatorResult:
    issues: list[ValidationIssue] = []

    if not blueprint.generation_contract.allowed_technologies:
        issues.append(
            ValidationIssue(
                code="MISSING_ALLOWED_TECHNOLOGIES",
                severity="error",
                message="Blueprint has no allowed technologies.",
            )
        )

    if not any(blueprint.priority_skills.get(level) for level in ["P1", "P2", "P3", "P4"]):
        issues.append(
            ValidationIssue(
                code="MISSING_PRIORITY_SKILLS",
                severity="error",
                message="Blueprint has no priority skills.",
            )
        )

    if not blueprint.job.primary_family:
        issues.append(
            ValidationIssue(
                code="MISSING_PRIMARY_FAMILY",
                severity="error",
                message="Blueprint has no primary family.",
            )
        )

    return ValidatorResult(
        name="blueprint_validator",
        passed=not any(issue.severity == "error" for issue in issues),
        score=100.0 if not issues else 0.0,
        issues=issues,
    )
