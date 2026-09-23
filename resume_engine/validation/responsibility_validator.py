from resume_engine.config import thresholds
from resume_engine.generation.bullet_enrichment import attach_bullet_metadata
from resume_engine.models.jd_blueprint import JDBlueprint
from resume_engine.models.resume_schema import ResumeJSON
from resume_engine.models.validation_schema import ValidationIssue, ValidatorResult
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


def _bigrams(text: str) -> set[str]:
    words = [w for w in normalize_text(text).replace("/", " ").replace("-", " ").split() if w]
    return {" ".join(words[i : i + 2]) for i in range(len(words) - 1)}


def _responsibility_score(required: set[str], required_text: str, bullet_text: str, technologies: list[str]) -> float:
    """Keyword overlap with bigram boost and technology evidence (Gate 2)."""
    bullet_words = _keywords(bullet_text)
    if not required:
        base = 0.5
    else:
        base = len(required & bullet_words) / len(required)

    bigram_boost = 0.0
    req_bigrams = _bigrams(required_text)
    bullet_bigrams = _bigrams(bullet_text)
    if req_bigrams:
        bigram_boost = 0.25 * (len(req_bigrams & bullet_bigrams) / len(req_bigrams))

    tech_boost = 0.1 * len(
        [
            tech
            for tech in technologies
            if normalize_text(tech) in normalize_text(required_text)
            or tech.lower() in required_text.lower()
        ]
    )
    return min(1.0, base + bigram_boost + tech_boost)


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

    Gate 2: keyword overlap + bigram phrase boost + technology evidence.
    Semantic Laya assist consumes uncovered_responsibility_ids separately.
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
            score = _responsibility_score(
                required,
                text,
                bullet.text,
                list(bullet.technologies or []),
            )
            # Prefer bullets already tagged with this R id (slight boost).
            if rid in bullet.responsibility_ids:
                score = min(1.0, score + 0.05)
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
    uncovered_ids = [
        rid for rid, info in mapping.items() if info.get("status") == "FAIL"
    ]

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
            "uncovered_responsibility_ids": uncovered_ids,
            "match_method": "keyword_overlap_v2",
        },
    )
