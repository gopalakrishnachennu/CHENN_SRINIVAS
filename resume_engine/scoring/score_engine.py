from resume_engine.models.validation_schema import ValidatorResult
from resume_engine.scoring.score_weights import SCORE_WEIGHTS


def _result(results: list[ValidatorResult], name: str) -> ValidatorResult | None:
    return next((item for item in results if item.name == name), None)


def calculate_score(results: list[ValidatorResult]) -> tuple[float, dict[str, float]]:
    coverage = _result(results, "coverage_validator")
    responsibility = _result(results, "responsibility_validator")
    role = _result(results, "role_drift_validator")
    hybrid = _result(results, "hybrid_family_validator")
    ai_placement = _result(results, "ai_tool_placement_validator")
    technology = _result(results, "technology_firewall")
    duplicate = _result(results, "duplicate_validator")
    ats = _result(results, "ats_validator")
    laya = _result(results, "laya_validator")

    p1 = 100.0
    p2 = 100.0
    p3 = 100.0
    if coverage:
        p1 = coverage.details.get("P1_coverage", 1.0) * 100
        p2 = coverage.details.get("P2_coverage", 1.0) * 100
        p3 = coverage.details.get("P3_coverage", 1.0) * 100

    subscores = {
        "p1_coverage": round(p1, 2),
        "p2_coverage": round(p2, 2),
        "responsibility_coverage": responsibility.score if responsibility else 0.0,
        "role_alignment": min(
            role.score if role else 0.0,
            hybrid.score if hybrid else 100.0,
            laya.score if laya else 100.0,
        ),
        "technology_alignment": technology.score if technology else 0.0,
        "keyword_distribution": min(
            round((p1 * 0.5) + (p2 * 0.3) + (p3 * 0.2), 2),
            ai_placement.score if ai_placement else 100.0,
        ),
        "bullet_quality": laya.score if laya else 85.0,
        "duplicate_safety": duplicate.score if duplicate else 0.0,
        "ats_structure": ats.score if ats else 0.0,
    }

    weighted = 0.0
    total_weight = sum(SCORE_WEIGHTS.values())
    for key, weight in SCORE_WEIGHTS.items():
        weighted += subscores[key] * weight

    return round(weighted / total_weight, 2), subscores
