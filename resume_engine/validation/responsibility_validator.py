from resume_engine.config import thresholds
from resume_engine.models.jd_blueprint import JDBlueprint
from resume_engine.models.resume_schema import ResumeJSON
from resume_engine.models.validation_schema import ValidationIssue, ValidatorResult
from resume_engine.generation.bullet_enrichment import attach_bullet_metadata
from resume_engine.validation.text_utils import normalize_text


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


def _ensure_bullet_meta(blueprint: JDBlueprint, resume: ResumeJSON) -> ResumeJSON:
    needs = any(not exp.bullet_meta for exp in resume.experience) or any(
        not project.bullet_meta for project in resume.projects
    )
    if needs:
        return attach_bullet_metadata(blueprint, resume)
    return resume


def validate_responsibilities(blueprint: JDBlueprint, resume: ResumeJSON) -> ValidatorResult:
    """
    Map each JD responsibility (R001...) to the best aligned bullet.
    Deterministic overlap + technology match first.
    """
    resume = _ensure_bullet_meta(blueprint, resume)
    bullets = []
    for exp in resume.experience:
        bullets.extend(exp.bullet_meta)
    for project in resume.projects:
        bullets.extend(project.bullet_meta)

    mapping: dict[str, dict] = {}
    issues: list[ValidationIssue] = []
    covered_count = 0

    for entry in blueprint.responsibility_entries():
        rid = entry["id"]
        text = entry["text"]
        required = _keywords(text)
        best_id = None
        best_score = 0.0

        for bullet in bullets:
            if rid in bullet.responsibility_ids:
                # Prefer explicit mapping score recomputed
                bullet_words = _keywords(bullet.text)
                overlap = (
                    1.0
                    if not required
                    else len(required & bullet_words) / max(1, len(required))
                )
                tech_boost = 0.1 * len(
                    [
                        tech
                        for tech in bullet.technologies
                        if normalize_text(tech) in normalize_text(text)
                        or tech.lower() in text.lower()
                    ]
                )
                score = min(1.0, overlap + tech_boost)
            else:
                bullet_words = _keywords(bullet.text)
                if not required:
                    score = 0.5
                else:
                    score = len(required & bullet_words) / len(required)
            if score > best_score:
                best_score = score
                best_id = bullet.id

        passed = best_score >= 0.45
        if passed:
            covered_count += 1
            mapping[rid] = {
                "responsibility": text,
                "bullet_id": best_id,
                "status": "PASS",
                "score": round(best_score, 2),
            }
        else:
            mapping[rid] = {
                "responsibility": text,
                "bullet_id": best_id,
                "status": "FAIL",
                "score": round(best_score, 2),
            }
            issues.append(
                ValidationIssue(
                    code="FAIL_RESPONSIBILITY_COVERAGE",
                    severity="error",
                    message=f"{rid} is not sufficiently covered: {text}",
                    location=best_id,
                    repair_hint=f"Add or rewrite an experience bullet to cover {rid}: {text}",
                    metadata={
                        "responsibility_id": rid,
                        "responsibility": text,
                        "best_bullet_id": best_id,
                        "score": round(best_score, 2),
                    },
                )
            )

    total = max(1, len(mapping))
    ratio = covered_count / total
    passed = ratio >= thresholds.RESPONSIBILITY_COVERAGE_MIN

    report_lines = [
        f"{rid} -> {info['bullet_id'] or 'NONE'} {info['status']} {info['score']:.2f}"
        for rid, info in mapping.items()
    ]

    return ValidatorResult(
        name="responsibility_validator",
        passed=passed,
        score=round(ratio * 100, 2),
        issues=issues,
        details={
            "responsibility_mapping": mapping,
            "mapping_report": report_lines,
            "covered": covered_count,
            "total": len(mapping),
        },
    )
