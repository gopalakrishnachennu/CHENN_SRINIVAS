from resume_engine.config import thresholds
from resume_engine.models.resume_schema import ResumeJSON
from resume_engine.models.validation_schema import ValidationIssue, ValidatorResult
from resume_engine.validation.text_utils import all_bullets, normalize_text, similarity


def validate_duplicates(resume: ResumeJSON) -> ValidatorResult:
    bullets = all_bullets(resume)
    issues: list[ValidationIssue] = []

    for i, (loc_a, bullet_a) in enumerate(bullets):
        for loc_b, bullet_b in bullets[i + 1 :]:
            if normalize_text(bullet_a) == normalize_text(bullet_b):
                issues.append(
                    ValidationIssue(
                        code="FAIL_EXACT_DUPLICATE_BULLET",
                        severity="error",
                        message="Exact duplicate resume bullet found.",
                        location=f"{loc_a} / {loc_b}",
                        repair_hint="Rewrite or remove one duplicate bullet.",
                    )
                )
            else:
                ratio = similarity(bullet_a, bullet_b)
                if ratio >= thresholds.DUPLICATE_SIMILARITY_MAX:
                    issues.append(
                        ValidationIssue(
                            code="WARN_NEAR_DUPLICATE_BULLET",
                            severity="warning",
                            message=f"Near-duplicate bullet pair found ({ratio:.2f}).",
                            location=f"{loc_a} / {loc_b}",
                            repair_hint="Rewrite one bullet with a different action, technology, or result pattern.",
                            metadata={"similarity": ratio},
                        )
                    )

    error_count = sum(1 for issue in issues if issue.severity == "error")
    score = max(0.0, 100.0 - (error_count * 25) - ((len(issues) - error_count) * 8))

    return ValidatorResult(
        name="duplicate_validator",
        passed=error_count == 0,
        score=round(score, 2),
        issues=issues,
        details={"bullet_count": len(bullets), "duplicate_issue_count": len(issues)},
    )
