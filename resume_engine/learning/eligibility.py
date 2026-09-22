"""Eligibility gates for strategy-learning feedback (Wave 3).

Only successful, high-quality outcomes may influence future strategy ranking.
Failed or soft-broken runs are persisted for analysis but never used for ranking.
"""

from __future__ import annotations

from resume_engine.config import thresholds

# Hard-fail codes that disqualify a record even if `passed` was mis-set historically.
TECHNOLOGY_FIREWALL_CODES = frozenset(
    {
        "FAIL_UNAPPROVED_TECHNOLOGY",
        "FAIL_UNAPPROVED_BULLET_TECHNOLOGY",
        "FAIL_LLM_GENERATED_TECHNOLOGY",
        "FAIL_UNAPPROVED_TECHNOLOGY_IN_TEXT",
    }
)
ROLE_DRIFT_CODES = frozenset({"FAIL_ROLE_DRIFT"})


def _failure_codes(record: dict) -> set[str]:
    codes = record.get("failure_codes")
    if codes is None:
        codes = record.get("failures") or []
    return {str(code) for code in codes}


def is_hybrid_blueprint(
    secondary_family: str | None,
    hybrid_probability: float | None,
) -> bool:
    secondary = secondary_family or "none"
    probability = float(hybrid_probability or 0.0)
    return secondary != "none" and probability >= thresholds.LEARNING_HYBRID_PROBABILITY_MIN


def is_record_eligible_for_learning(record: dict) -> bool:
    """
    Strategy-learning eligibility (Phase 2.7 Gate 1):

    - passed == true
    - eligible_for_learning not explicitly false
    - is_final_selection == true (default true for legacy records)
    - superseded == false
    - no technology firewall errors
    - no role drift
    - P1 == 100%
    - P2 >= 90%
    """
    passed = record.get("passed")
    if passed is None:
        passed = record.get("successful_pattern")
    if not passed:
        return False

    if record.get("eligible_for_learning") is False:
        return False

    if record.get("superseded") is True:
        return False

    if record.get("is_final_selection") is False:
        return False

    if record.get("status") == "PIPELINE_ERROR":
        return False

    codes = _failure_codes(record)
    if codes & TECHNOLOGY_FIREWALL_CODES:
        return False
    if codes & ROLE_DRIFT_CODES:
        return False

    if record.get("technology_firewall_passed") is False:
        return False
    if record.get("role_drift_passed") is False:
        return False

    p1 = float(record.get("p1_coverage") if record.get("p1_coverage") is not None else -1.0)
    p2 = float(record.get("p2_coverage") if record.get("p2_coverage") is not None else -1.0)
    if p1 < thresholds.LEARNING_P1_MIN:
        return False
    if p2 < thresholds.LEARNING_P2_MIN:
        return False

    return True
