from itertools import combinations

from resume_engine.models.resume_schema import ResumeJSON
from resume_engine.models.validation_schema import ValidationIssue, ValidatorResult
from resume_engine.validation.text_utils import flatten_resume_text, similarity


def validate_variant_similarity(
    resumes: list[ResumeJSON],
    threshold: float = 0.92,
) -> ValidatorResult:
    issues: list[ValidationIssue] = []

    for left, right in combinations(resumes, 2):
        left_id = left.variant_id or "unknown_left"
        right_id = right.variant_id or "unknown_right"
        ratio = similarity(flatten_resume_text(left), flatten_resume_text(right))
        if ratio >= threshold:
            issues.append(
                ValidationIssue(
                    code="FAIL_VARIANT_DUPLICATION",
                    severity="error",
                    message=f"{left_id} and {right_id} are too similar ({ratio:.2f}).",
                    location=f"{left_id}/{right_id}",
                    repair_hint=f"Regenerate {right_id} with stronger emphasis on its variant strategy.",
                    metadata={"similarity": ratio},
                )
            )

    score = 100.0 if not issues else max(0.0, 100.0 - len(issues) * 20)
    return ValidatorResult(
        name="variant_similarity_validator",
        passed=not issues,
        score=round(score, 2),
        issues=issues,
        details={"variant_count": len(resumes), "threshold": threshold},
    )
