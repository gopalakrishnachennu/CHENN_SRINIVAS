from resume_engine.config import thresholds
from resume_engine.models.jd_blueprint import JDBlueprint
from resume_engine.models.resume_schema import ResumeJSON
from resume_engine.models.validation_schema import ValidationIssue, ValidatorResult
from resume_engine.validation.text_utils import flatten_experience_text, normalize_text


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


def validate_responsibilities(blueprint: JDBlueprint, resume: ResumeJSON) -> ValidatorResult:
    experience_text = flatten_experience_text(resume)
    resume_words = _keywords(experience_text)
    coverage: dict[str, bool] = {}
    issues: list[ValidationIssue] = []

    for responsibility in blueprint.responsibilities:
        required_words = _keywords(responsibility)
        if not required_words:
            covered = True
        else:
            overlap = len(required_words & resume_words) / len(required_words)
            covered = overlap >= 0.45

        coverage[responsibility] = covered
        if not covered:
            issues.append(
                ValidationIssue(
                    code="FAIL_RESPONSIBILITY_COVERAGE",
                    severity="error",
                    message=f"Resume does not sufficiently cover JD responsibility: {responsibility}",
                    repair_hint=f"Add or rewrite an experience bullet to cover: {responsibility}",
                    metadata={"responsibility": responsibility},
                )
            )

    covered_count = sum(1 for value in coverage.values() if value)
    total = max(1, len(coverage))
    ratio = covered_count / total
    passed = ratio >= thresholds.RESPONSIBILITY_COVERAGE_MIN

    return ValidatorResult(
        name="responsibility_validator",
        passed=passed,
        score=round(ratio * 100, 2),
        issues=issues,
        details={"responsibility_coverage": coverage, "covered": covered_count, "total": len(coverage)},
    )
