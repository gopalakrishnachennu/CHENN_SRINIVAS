"""P4 optional adjacent usage validator (Phase 2.7 Gate 1 semantics)."""

from resume_engine.config import thresholds
from resume_engine.models.jd_blueprint import JDBlueprint
from resume_engine.models.resume_schema import ResumeJSON
from resume_engine.models.validation_schema import ValidationIssue, ValidatorResult
from resume_engine.validation.text_utils import contains_term, flatten_resume_text


def validate_p4_usage(blueprint: JDBlueprint, resume: ResumeJSON) -> ValidatorResult:
    """
    P4 = approved adjacent / optional / supporting.

    Hard gate uses share of *used* priority skills (not available-P4 ratio):

      used_required = unique detected P1+P2+P3
      used_p4 = unique detected P4
      p4_share = len(used_p4) / max(1, len(used_required)+len(used_p4))

    PASS when used_p4==0 OR used_p4==1 (one-P4 floor) OR p4_share <= P4_USAGE_MAX.

    Missing P4 never fails. Available-P4 ratio is diagnostic only.
    """
    p4_available = list(blueprint.priority_skills.get("P4", []))
    p1 = list(blueprint.priority_skills.get("P1", []))
    p2 = list(blueprint.priority_skills.get("P2", []))
    p3 = list(blueprint.priority_skills.get("P3", []))
    max_ratio = thresholds.P4_USAGE_MAX
    resume_text = flatten_resume_text(resume)

    p4_used = [skill for skill in p4_available if contains_term(resume_text, skill)]
    required_priority_used = []
    for skill in p1 + p2 + p3:
        if skill and skill not in required_priority_used and contains_term(resume_text, skill):
            required_priority_used.append(skill)

    used_p4_count = len(p4_used)
    required_count = len(required_priority_used)
    priority_skill_total = required_count + used_p4_count
    p4_share = used_p4_count / max(1, priority_skill_total)
    available_p4_ratio = (used_p4_count / len(p4_available)) if p4_available else 0.0

    one_p4_floor_applied = used_p4_count == 1
    passes = (
        used_p4_count == 0
        or used_p4_count == 1
        or p4_share <= max_ratio
    )

    issues: list[ValidationIssue] = []
    if not passes:
        issues.append(
            ValidationIssue(
                code="FAIL_P4_OVERUSE",
                severity="error",
                message=(
                    f"P4 share of used priority skills {p4_share:.2f} exceeds "
                    f"configured maximum {max_ratio:.2f} "
                    f"(used_p4={used_p4_count}, required_used={required_count})."
                ),
                repair_hint=(
                    "Reduce optional adjacent (P4) technologies; keep at most one "
                    "or ensure P4 does not dominate used priority skills."
                ),
                metadata={
                    "p4_available": p4_available,
                    "p4_used": p4_used,
                    "p4_usage_count": used_p4_count,
                    "required_priority_used": required_priority_used,
                    "required_priority_used_count": required_count,
                    "p4_share_of_used_priority": round(p4_share, 4),
                    "available_p4_ratio": round(available_p4_ratio, 4),
                    "max_ratio": max_ratio,
                    "one_p4_floor_applied": one_p4_floor_applied,
                },
            )
        )

    if passes:
        score = 100.0
    else:
        score = max(0.0, 100.0 - (p4_share - max_ratio) * 200)

    details = {
        "p4_available": p4_available,
        "p4_used": p4_used,
        "p4_usage_count": used_p4_count,
        "required_priority_used": required_priority_used,
        "required_priority_used_count": required_count,
        "p4_share_of_used_priority": round(p4_share, 4),
        "available_p4_ratio": round(available_p4_ratio, 4),
        # Backward-compatible diagnostic alias (NOT the hard gate).
        "usage_ratio": round(available_p4_ratio, 4),
        "max_ratio": max_ratio,
        "one_p4_floor_applied": one_p4_floor_applied,
    }

    return ValidatorResult(
        name="p4_usage_validator",
        passed=passes,
        score=round(score, 2),
        issues=issues,
        details=details,
    )
