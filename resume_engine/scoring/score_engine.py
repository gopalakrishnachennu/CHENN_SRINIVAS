from resume_engine.config import thresholds
from resume_engine.models.resume_schema import ResumeJSON
from resume_engine.models.resume_strategy import VariantStrategy
from resume_engine.models.validation_schema import ValidatorResult
from resume_engine.scoring.score_weights import SCORE_WEIGHTS
from resume_engine.validation.variant_regeneration import variant_focus_score
from resume_engine.validation.text_utils import flatten_resume_text


def _result(results: list[ValidatorResult], name: str) -> ValidatorResult | None:
    return next((item for item in results if item.name == name), None)


def calculate_score(results: list[ValidatorResult]) -> tuple[float, dict[str, float]]:
    """
    Internal JD compatibility / optimization score.

    This is NOT an external ATS marketing score.
    Exposed name in reports: JD_COMPATIBILITY_SCORE (alias of optimization_score).
    """
    coverage = _result(results, "coverage_validator")
    responsibility = _result(results, "responsibility_validator")
    role = _result(results, "role_drift_validator")
    hybrid = _result(results, "hybrid_family_validator")
    ai_placement = _result(results, "ai_tool_placement_validator")
    technology = _result(results, "technology_firewall")
    duplicate = _result(results, "duplicate_validator")
    ats = _result(results, "ats_validator")
    laya = _result(results, "laya_validator")
    p4 = _result(results, "p4_usage_validator")

    p1 = 100.0
    p2 = 100.0
    p3 = 100.0
    if coverage:
        p1 = coverage.details.get("P1_coverage", 1.0) * 100
        p2 = coverage.details.get("P2_coverage", 1.0) * 100
        p3 = coverage.details.get("P3_coverage", 1.0) * 100

    p4_usage_score = 100.0
    if p4:
        share = float(
            p4.details.get(
                "p4_share_of_used_priority",
                p4.details.get("usage_ratio", 0.0),
            )
        )
        max_ratio = float(p4.details.get("max_ratio", thresholds.P4_USAGE_MAX))
        used_count = int(p4.details.get("p4_usage_count", 0))
        if used_count <= 1 or share <= max_ratio:
            p4_usage_score = 100.0
        else:
            p4_usage_score = max(0.0, 100.0 - (share - max_ratio) * 200)

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
        "technology_safety": technology.score if technology else 0.0,
        "keyword_distribution": min(
            round((p1 * 0.5) + (p2 * 0.3) + (p3 * 0.2), 2),
            ai_placement.score if ai_placement else 100.0,
        ),
        "ai_placement": ai_placement.score if ai_placement else 100.0,
        "bullet_quality": laya.score if laya else 85.0,
        "duplicate_safety": duplicate.score if duplicate else 0.0,
        "p4_usage": round(p4_usage_score, 2),
        "ats_structure": ats.score if ats else 0.0,
        "responsibility_fit": responsibility.score if responsibility else 0.0,
    }

    weighted = 0.0
    total_weight = sum(SCORE_WEIGHTS.values())
    for key, weight in SCORE_WEIGHTS.items():
        weighted += subscores[key] * weight

    jd_compatibility_score = round(weighted / total_weight, 2)
    # Keep optimization_score key compatibility via caller; diagnostics include alias.
    subscores["JD_COMPATIBILITY_SCORE"] = jd_compatibility_score
    subscores["INTERNAL_JD_OPTIMIZATION_SCORE"] = jd_compatibility_score
    return jd_compatibility_score, subscores


def classify_score_delta(score_a: float, score_b: float) -> str:
    if abs(score_a - score_b) < thresholds.SCORE_COMPARABLE_EPSILON:
        return "COMPARABLE"
    return "DISTINCT"


def build_variant_diagnostics(
    resume: ResumeJSON,
    variant: VariantStrategy,
    subscores: dict[str, float],
) -> dict:
    focus = variant_focus_score(resume, variant)
    return {
        "variant_id": resume.variant_id,
        "variant_positioning": variant.positioning,
        "variant_focus_score": focus,
        "p1_coverage": subscores.get("p1_coverage"),
        "p2_coverage": subscores.get("p2_coverage"),
        "responsibility_fit": subscores.get("responsibility_fit"),
        "role_alignment": subscores.get("role_alignment"),
        "technology_safety": subscores.get("technology_safety"),
        "ai_placement": subscores.get("ai_placement"),
        "bullet_quality": subscores.get("bullet_quality"),
        "duplicate_safety": subscores.get("duplicate_safety"),
        "p4_usage": subscores.get("p4_usage"),
        "text_length": len(flatten_resume_text(resume)),
    }
