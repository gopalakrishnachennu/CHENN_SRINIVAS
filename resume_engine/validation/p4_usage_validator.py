from resume_engine.config import thresholds
from resume_engine.models.jd_blueprint import JDBlueprint
from resume_engine.models.resume_schema import ResumeJSON
from resume_engine.models.validation_schema import ValidationIssue, ValidatorResult
from resume_engine.validation.text_utils import contains_term, flatten_resume_text


def validate_p4_usage(blueprint: JDBlueprint, resume: ResumeJSON) -> ValidatorResult:
    """P4 skills are optional adjacent support. Overuse fails; absence never fails."""
    p4_available = list(blueprint.priority_skills.get("P4", []))
    max_ratio = thresholds.P4_USAGE_MAX

    if not p4_available:
        return ValidatorResult(
            name="p4_usage_validator",
            passed=True,
            score=100.0,
            issues=[],
            details={
                "p4_available": [],
                "p4_used": [],
                "p4_usage_count": 0,
                "usage_ratio": 0.0,
                "max_ratio": max_ratio,
            },
        )

    resume_text = flatten_resume_text(resume)
    p4_used = [skill for skill in p4_available if contains_term(resume_text, skill)]
    usage_ratio = len(p4_used) / len(p4_available)

    issues: list[ValidationIssue] = []
    if usage_ratio > max_ratio:
        issues.append(
            ValidationIssue(
                code="FAIL_P4_OVERUSE",
                severity="error",
                message=(
                    f"P4 usage ratio {usage_ratio:.2f} exceeds configured maximum {max_ratio:.2f}."
                ),
                repair_hint=(
                    "Reduce optional adjacent (P4) technologies; keep only the most relevant support skills."
                ),
                metadata={
                    "p4_available": p4_available,
                    "p4_used": p4_used,
                    "usage_ratio": round(usage_ratio, 4),
                    "max_ratio": max_ratio,
                },
            )
        )

    score = 100.0 if not issues else max(0.0, 100.0 - (usage_ratio - max_ratio) * 200)
    return ValidatorResult(
        name="p4_usage_validator",
        passed=not issues,
        score=round(score, 2),
        issues=issues,
        details={
            "p4_available": p4_available,
            "p4_used": p4_used,
            "p4_usage_count": len(p4_used),
            "usage_ratio": round(usage_ratio, 4),
            "max_ratio": max_ratio,
        },
    )
