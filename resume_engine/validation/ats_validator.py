from resume_engine.config import thresholds
from resume_engine.models.resume_schema import ResumeJSON
from resume_engine.models.validation_schema import ValidationIssue, ValidatorResult
from resume_engine.validation.text_utils import all_bullets

UNSAFE_CHARACTERS = {"▸", "◆", "■", "●", "✓", "✗"}


def validate_ats(resume: ResumeJSON) -> ValidatorResult:
    issues: list[ValidationIssue] = []

    if not resume.summary:
        issues.append(
            ValidationIssue(
                code="FAIL_MISSING_SUMMARY",
                severity="error",
                message="Resume is missing professional summary.",
            )
        )

    if not resume.technical_skills:
        issues.append(
            ValidationIssue(
                code="FAIL_MISSING_TECHNICAL_SKILLS",
                severity="error",
                message="Resume is missing technical skills.",
            )
        )

    if not resume.experience:
        issues.append(
            ValidationIssue(
                code="FAIL_MISSING_EXPERIENCE",
                severity="error",
                message="Resume is missing experience section.",
            )
        )

    text = "\n".join([resume.summary, *[b for _, b in all_bullets(resume)]])
    for char in UNSAFE_CHARACTERS:
        if char in text:
            issues.append(
                ValidationIssue(
                    code="WARN_FORMAT_UNSAFE_CHARACTER",
                    severity="warning",
                    message=f"ATS-unsafe decorative character found: {char}",
                    repair_hint="Use plain ASCII punctuation.",
                )
            )

    for location, bullet in all_bullets(resume):
        word_count = len(bullet.split())
        if word_count < thresholds.BULLET_WORD_MIN or word_count > thresholds.BULLET_WORD_MAX:
            issues.append(
                ValidationIssue(
                    code="WARN_BULLET_LENGTH",
                    severity="warning",
                    message=f"Bullet length is {word_count} words; target range is {thresholds.BULLET_WORD_MIN}-{thresholds.BULLET_WORD_MAX}.",
                    location=location,
                    repair_hint="Rewrite bullet to a concise ATS-friendly length.",
                    metadata={"word_count": word_count},
                )
            )

    error_count = sum(1 for issue in issues if issue.severity == "error")
    warning_count = len(issues) - error_count
    score = max(0.0, 100.0 - (error_count * 30) - (warning_count * 3))

    return ValidatorResult(
        name="ats_validator",
        passed=error_count == 0,
        score=round(score, 2),
        issues=issues,
        details={
            "standard_headings": True,
            "tables": False,
            "graphics": False,
            "columns": False,
            "format_safe": error_count == 0,
        },
    )
