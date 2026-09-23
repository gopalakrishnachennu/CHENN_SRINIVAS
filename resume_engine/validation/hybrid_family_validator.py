from resume_engine.models.jd_blueprint import JDBlueprint
from resume_engine.models.resume_schema import ResumeJSON
from resume_engine.models.validation_schema import ValidationIssue, ValidatorResult
from resume_engine.validation.text_utils import contains_term, flatten_resume_text

FAMILY_TERMS = {
    "devops_cloud": ["AWS", "Azure", "GCP", "Terraform", "Kubernetes", "CI/CD", "Docker", "Helm", "cloud infrastructure"],
    "data_engineering": ["Databricks", "Apache Spark", "Spark", "PySpark", "Delta Lake", "ETL", "pipeline", "data platform"],
    "ai_ml": ["OpenAI API", "Claude API", "LangChain", "LangGraph", "RAG", "embeddings", "LLM"],
    "software_engineering": ["API", "backend", "service", "application", "software"],
    "data_analytics": ["dashboard", "reporting", "analytics", "Power BI", "Tableau"],
    "infrastructure_support": ["server", "network", "data center", "support"],
    "test_engineering": ["test", "validation", "QA", "automation"],
}

UNRELATED_ROLE_TERMS = ["Data Scientist", "Frontend Engineer", "Salesforce Engineer", "Salesforce Administrator"]


def _represented(text: str, family: str) -> bool:
    return any(contains_term(text, term) for term in FAMILY_TERMS.get(family, []))


def validate_hybrid_family_retention(blueprint: JDBlueprint, resume: ResumeJSON) -> ValidatorResult:
    text = flatten_resume_text(resume)
    issues: list[ValidationIssue] = []
    primary = blueprint.job.primary_family
    secondary = blueprint.job.secondary_family
    hybrid_expected = secondary != "none" and blueprint.job.hybrid_probability >= 0.55

    primary_represented = _represented(text, primary)
    secondary_represented = True if not hybrid_expected else _represented(text, secondary)
    unrelated_terms = [term for term in UNRELATED_ROLE_TERMS if contains_term(text, term)]

    if not primary_represented:
        issues.append(
            ValidationIssue(
                code="FAIL_PRIMARY_FAMILY_NOT_REPRESENTED",
                severity="error",
                message=f"Resume does not sufficiently represent primary family: {primary}",
                repair_hint=f"Add stronger {primary} positioning using approved technologies.",
                metadata={"primary_family": primary},
            )
        )

    if hybrid_expected and not secondary_represented:
        issues.append(
            ValidationIssue(
                code="FAIL_SECONDARY_FAMILY_NOT_RETAINED",
                severity="error",
                message=f"Hybrid JD secondary family is missing from resume: {secondary}",
                repair_hint=f"Add stronger {secondary} positioning using approved technologies.",
                metadata={"secondary_family": secondary},
            )
        )

    for term in unrelated_terms:
        issues.append(
            ValidationIssue(
                code="FAIL_UNRELATED_THIRD_FAMILY",
                severity="error",
                message=f"Resume introduced unrelated role family term: {term}",
                repair_hint=f"Remove unrelated positioning: {term}.",
                metadata={"term": term},
            )
        )

    return ValidatorResult(
        name="hybrid_family_validator",
        passed=not issues,
        score=100.0 if not issues else 50.0,
        issues=issues,
        details={
            "hybrid_expected": hybrid_expected,
            "primary_family": primary,
            "secondary_family": secondary,
            "primary_represented": primary_represented,
            "secondary_represented": secondary_represented,
            "unrelated_terms": unrelated_terms,
        },
    )
