from resume_engine.models.jd_blueprint import JDBlueprint
from resume_engine.models.resume_schema import ResumeJSON
from resume_engine.models.validation_schema import ValidationIssue, ValidatorResult
from resume_engine.validation.text_utils import contains_term, flatten_resume_text

ROLE_DRIFT_TERMS = {
    "data scientist": "ai_ml",
    "machine learning researcher": "ai_ml",
    "frontend developer": "software_engineering",
    "salesforce administrator": "other",
    "desktop support": "infrastructure_support",
}


def validate_role_drift(blueprint: JDBlueprint, resume: ResumeJSON) -> ValidatorResult:
    text = flatten_resume_text(resume)
    issues: list[ValidationIssue] = []

    target_title = blueprint.job.target_title or ""
    if target_title and not contains_term(resume.target_title + " " + resume.summary, target_title.split()[0]):
        issues.append(
            ValidationIssue(
                code="WARN_TITLE_ALIGNMENT_WEAK",
                severity="warning",
                message="Resume title/summary may not clearly align with the target role.",
                repair_hint=f"Align target_title and summary with {target_title}.",
            )
        )

    for term, family in ROLE_DRIFT_TERMS.items():
        if family != blueprint.job.primary_family and contains_term(text, term):
            issues.append(
                ValidationIssue(
                    code="FAIL_ROLE_DRIFT",
                    severity="error",
                    message=f"Resume appears to drift toward unrelated role identity: {term}",
                    repair_hint=f"Remove or de-emphasize {term} positioning.",
                    metadata={"term": term, "blueprint_primary_family": blueprint.job.primary_family},
                )
            )

    errors = [issue for issue in issues if issue.severity == "error"]
    score = 100.0 if not errors else 40.0
    if issues and not errors:
        score = 88.0

    return ValidatorResult(
        name="role_drift_validator",
        passed=not errors,
        score=score,
        issues=issues,
        details={
            "primary_family": blueprint.job.primary_family,
            "secondary_family": blueprint.job.secondary_family,
        },
    )
