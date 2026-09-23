"""Reward engine for online learning observations (Phase 2.8)."""

from __future__ import annotations

from typing import Any

from resume_engine.config import thresholds
from resume_engine.learning.eligibility import is_record_eligible_for_learning
from resume_engine.learning.online.config import ONLINE_MAX_REWARD, ONLINE_MIN_REWARD
from resume_engine.learning.online.schemas import RewardResult

# Weights sum to 1.00
REWARD_WEIGHTS: dict[str, float] = {
    "p1": 0.20,
    "p2": 0.12,
    "responsibility": 0.15,
    "role_alignment": 0.12,
    "technology_alignment": 0.10,
    "laya_alignment": 0.08,
    "variant_focus": 0.08,
    "duplicate_safety": 0.05,
    "cross_run_uniqueness": 0.05,
    "repair_efficiency": 0.05,
}


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _norm_pct(value: Any, *, default: float = 0.0) -> float:
    """Normalize 0–100 style metrics (or 0–1 ratios) into [0, 1]."""
    if value is None:
        return default
    number = float(value)
    if number > 1.0:
        return _clamp01(number / 100.0)
    return _clamp01(number)


def is_online_trainable(record: dict[str, Any]) -> bool:
    """Reuse existing eligibility; require explicit final + not superseded."""
    if record.get("is_final_selection") is False:
        return False
    if record.get("superseded") is True:
        return False
    if record.get("status") == "PIPELINE_ERROR":
        return False
    return is_record_eligible_for_learning(record)


def compute_reward(record: dict[str, Any]) -> RewardResult:
    """
    Combine validated final metrics into a bounded reward.

    Hard zeros for firewall / role drift / P1 miss / failed / non-trainable.
    """
    if record.get("superseded") is True:
        return RewardResult(reward=0.0, components={}, trainable=False, zero_reason="superseded")
    if record.get("is_final_selection") is False:
        return RewardResult(reward=0.0, components={}, trainable=False, zero_reason="not_final")
    if record.get("status") == "PIPELINE_ERROR":
        return RewardResult(reward=0.0, components={}, trainable=False, zero_reason="pipeline_error")
    if not record.get("passed"):
        return RewardResult(reward=0.0, components={}, trainable=False, zero_reason="failed")

    if record.get("technology_firewall_passed") is False:
        return RewardResult(reward=0.0, components={"technology_alignment": 0.0}, trainable=False, zero_reason="firewall")
    if record.get("role_drift_passed") is False:
        return RewardResult(reward=0.0, components={"role_alignment": 0.0}, trainable=False, zero_reason="role_drift")

    p1 = _norm_pct(record.get("p1_coverage"), default=-1.0)
    if p1 < 1.0 - 1e-9:
        return RewardResult(
            reward=0.0,
            components={"p1": p1 if p1 >= 0 else 0.0},
            trainable=False,
            zero_reason="p1_incomplete",
        )

    if record.get("truthfulness_passed") is False or record.get("candidate_truthfulness_passed") is False:
        return RewardResult(reward=0.0, components={}, trainable=False, zero_reason="truthfulness")

    # Soft P4 overuse: if p4_usage score is very low, zero (final invalid-like).
    p4 = _norm_pct(record.get("p4_usage"), default=1.0)
    if p4 < 0.5 and record.get("passed") is False:
        return RewardResult(reward=0.0, components={"p4_usage": p4}, trainable=False, zero_reason="p4_hard")

    components = {
        "p1": 1.0,
        "p2": _norm_pct(record.get("p2_coverage"), default=0.0),
        "responsibility": _norm_pct(record.get("responsibility_coverage"), default=0.0),
        "role_alignment": _norm_pct(record.get("role_alignment"), default=0.0),
        "technology_alignment": _norm_pct(record.get("technology_alignment"), default=0.0),
        "laya_alignment": _norm_pct(record.get("laya_alignment"), default=0.0),
        "variant_focus": _norm_pct(record.get("variant_focus_score"), default=0.5),
        "duplicate_safety": _norm_pct(record.get("duplicate_score"), default=0.0),
        "cross_run_uniqueness": _norm_pct(
            record.get("cross_run_uniqueness", record.get("cross_run_uniqueness_score")),
            default=1.0,
        ),
        "repair_efficiency": _repair_efficiency(record),
    }

    # Mild P4 penalty inside [0,1] when overused but still passed.
    if p4 < 1.0:
        components["technology_alignment"] = _clamp01(components["technology_alignment"] * (0.5 + 0.5 * p4))

    reward = 0.0
    for key, weight in REWARD_WEIGHTS.items():
        reward += weight * components.get(key, 0.0)
    reward = max(ONLINE_MIN_REWARD, min(ONLINE_MAX_REWARD, reward))

    trainable = is_online_trainable(record)
    if not trainable:
        return RewardResult(reward=0.0, components=components, trainable=False, zero_reason="ineligible")

    # Enforce configured P2 floor for trainable positive signal
    if components["p2"] * 100 < thresholds.LEARNING_P2_MIN - 1e-6:
        return RewardResult(reward=0.0, components=components, trainable=False, zero_reason="p2_below_threshold")

    return RewardResult(reward=reward, components=components, trainable=True, zero_reason=None)


def _repair_efficiency(record: dict[str, Any]) -> float:
    """1.0 if no repair needed; lower when many repairs or regression."""
    if record.get("repair_score_regression"):
        return 0.25
    repair_count = int(record.get("repair_count") or 0)
    if repair_count <= 0:
        return 1.0
    if repair_count == 1:
        return 0.7
    return max(0.2, 1.0 - 0.25 * repair_count)
