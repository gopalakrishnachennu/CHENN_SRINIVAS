"""Shadow-mode online learning: observe rankings without changing production."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from resume_engine.learning.online.config import (
    FEATURE_SCHEMA_VERSION,
    ONLINE_POLICY_VERSION,
    ONLINE_REWARD_SCHEMA_VERSION,
    evidence_allows_active,
    get_online_learning_mode,
    online_learning_enabled,
)
from resume_engine.learning.online.feature_builder import assert_no_pii, build_context_features
from resume_engine.learning.online.reward_engine import compute_reward
from resume_engine.learning.online.river_policy import (
    RiverStrategyPolicy,
    get_default_policy,
    reset_default_policy_for_tests,
)
from resume_engine.learning.online.schemas import ShadowDecision
from resume_engine.models.jd_blueprint import JDBlueprint

logger = logging.getLogger(__name__)

__all__ = [
    "observe_final_outcome",
    "record_shadow_decision",
    "record_shadow_decisions_for_variants",
    "reset_default_policy_for_tests",
]


def _candidate_actions(blueprint: JDBlueprint) -> list[str]:
    from resume_engine.strategy.variant_planner import list_all_candidate_positionings

    return list_all_candidate_positionings(blueprint)


def effective_mode(*, policy: RiverStrategyPolicy | None = None) -> str:
    mode = get_online_learning_mode()
    if mode != "active":
        return mode
    pol = policy or get_default_policy()
    if evidence_allows_active(
        observation_count=pol.observation_count,
        action_counts=pol.action_counts,
    ):
        logger.warning(
            "ONLINE_POLICY_FALLBACK: active requested but Gate 1.1 keeps shadow selection"
        )
    return "shadow"


def record_shadow_decisions_for_variants(
    *,
    blueprint: JDBlueprint,
    production_variants: list[tuple[str, str]],
    run_id: str,
    policy: RiverStrategyPolicy | None = None,
) -> list[ShadowDecision]:
    """
    Record ONE shadow decision per production variant.

    production_variants: [(variant_id, positioning), ...] in production order.
    Never mutates production order.
    """
    if not online_learning_enabled():
        return []
    mode = effective_mode(policy=policy)
    if mode == "disabled":
        return []

    decisions: list[ShadowDecision] = []
    try:
        eligible = _candidate_actions(blueprint)
        if not eligible:
            return []
        production_order = [pos for _, pos in production_variants]
        if not set(production_order).issubset(set(eligible)):
            logger.warning(
                "ONLINE_POLICY_FALLBACK: production actions outside candidate set"
            )
            return []

        context = build_context_features(blueprint)
        assert_no_pii(context)
        pol = policy or get_default_policy()
        ranked = pol.rank_actions(context, eligible)
        assert {p.action for p in ranked}.issubset(set(eligible))
        rank_by_action = {p.action: p.rank for p in ranked}
        shadow_top = ranked[0].action if ranked else None

        from resume_engine.learning.repository import get_default_repository

        repo = get_default_repository()
        for production_rank, (variant_id, production_action) in enumerate(
            production_variants, start=1
        ):
            decision = ShadowDecision(
                run_id=run_id,
                jd_hash=blueprint.jd_hash,
                variant_id=variant_id,
                context_version=FEATURE_SCHEMA_VERSION,
                policy_version=getattr(pol, "policy_version", ONLINE_POLICY_VERSION),
                mode=mode,
                available_actions=list(eligible),
                production_action=production_action,
                production_rank=production_rank,
                production_order=list(production_order),
                shadow_ranked_actions=ranked,
                shadow_top_action=shadow_top,
                shadow_rank_of_production_action=rank_by_action.get(production_action),
                shadow_agrees_with_production=bool(shadow_top == production_action),
                observation_count_at_prediction=pol.observation_count,
                created_at=datetime.now(UTC).isoformat(),
                context=context,
            )
            decision_id = repo.save_online_decision(decision.model_dump(mode="json"))
            decision.decision_id = decision_id
            decisions.append(decision)
        return decisions
    except Exception as exc:  # noqa: BLE001
        logger.warning("ONLINE_POLICY_FALLBACK: shadow decisions failed: %s", type(exc).__name__)
        return []


def record_shadow_decision(
    *,
    blueprint: JDBlueprint,
    production_order: list[str],
    run_id: str,
    variant_id: str | None = None,
    policy: RiverStrategyPolicy | None = None,
) -> ShadowDecision | None:
    """Backward-compatible single-call wrapper (uses synthetic V01.. if needed)."""
    if variant_id and len(production_order) == 1:
        variants = [(variant_id, production_order[0])]
    else:
        variants = [
            (f"V{index:02d}", action) for index, action in enumerate(production_order, start=1)
        ]
    decisions = record_shadow_decisions_for_variants(
        blueprint=blueprint,
        production_variants=variants,
        run_id=run_id,
        policy=policy,
    )
    return decisions[0] if decisions else None


def _validate_observation_fields(learning_record: dict[str, Any], action: str) -> str | None:
    for key in ("run_id", "jd_hash", "variant_id"):
        if not learning_record.get(key):
            return f"missing_{key}"
    if not action:
        return "missing_action"
    if learning_record.get("is_final_selection") is False:
        return "not_final"
    if learning_record.get("superseded") is True:
        return "superseded"
    if not learning_record.get("passed"):
        return "failed"
    return None


def observe_final_outcome(
    *,
    blueprint: JDBlueprint | None,
    learning_record: dict[str, Any],
    policy: RiverStrategyPolicy | None = None,
    persist_policy: bool = True,
) -> dict[str, Any] | None:
    """
    After finalization: compute reward and update River iff trainable.

    Consistency model (Gate 1.1):
      validate → idempotency check → River.observe → save policy → save observation APPLIED
    If policy save fails after in-memory observe, observation is still recorded as APPLIED
    to prevent double-training on retry; policy file may lag until next successful save.
    """
    if not online_learning_enabled():
        return None

    try:
        from resume_engine.learning.repository import get_default_repository

        repo = get_default_repository()
        action = learning_record.get("variant_positioning")
        run_id = learning_record.get("run_id")
        variant_id = learning_record.get("variant_id")
        policy_version = ONLINE_POLICY_VERSION

        # Idempotency: same final observation must not train twice.
        if run_id and variant_id and repo.has_applied_online_observation(
            run_id=str(run_id),
            variant_id=str(variant_id),
            policy_version=policy_version,
        ):
            return {
                "run_id": run_id,
                "variant_id": variant_id,
                "action": action,
                "eligible": False,
                "duplicate_observation_skipped": True,
                "zero_reason": "duplicate_observation_skipped",
                "policy_version": policy_version,
            }

        decision_row = None
        decision_id = None
        linkage_status = "decision_not_found"
        if run_id and variant_id:
            decision_row = repo.get_online_decision(
                run_id=str(run_id),
                variant_id=str(variant_id),
                policy_version=policy_version,
            )
            if decision_row:
                decision_id = int(decision_row["id"])
                linkage_status = "linked"

        reward_result = compute_reward(learning_record)
        field_err = _validate_observation_fields(learning_record, str(action or ""))
        observation: dict[str, Any] = {
            "decision_id": decision_id,
            "run_id": run_id,
            "jd_hash": learning_record.get("jd_hash"),
            "variant_id": variant_id,
            "action": action,
            "reward": reward_result.reward,
            "reward_components": reward_result.components,
            "eligible": False,
            "zero_reason": reward_result.zero_reason or field_err,
            "policy_version": policy_version,
            "reward_schema_version": ONLINE_REWARD_SCHEMA_VERSION,
            "linkage_status": linkage_status,
            "train_status": "SKIPPED",
        }

        if field_err or not reward_result.trainable:
            observation["zero_reason"] = field_err or reward_result.zero_reason
            repo.save_online_observation(observation)
            return observation

        if blueprint is None:
            observation["zero_reason"] = "missing_blueprint_context"
            observation["linkage_status"] = linkage_status
            repo.save_online_observation(observation)
            return observation

        context = build_context_features(blueprint)
        assert_no_pii(context)
        eligible = set(_candidate_actions(blueprint))
        if action not in eligible:
            observation["zero_reason"] = "action_not_eligible"
            repo.save_online_observation(observation)
            return observation

        pol = policy or get_default_policy()
        pol.observe(context, str(action), reward_result.reward)
        if persist_policy:
            try:
                pol.save()
            except Exception as exc:  # noqa: BLE001
                logger.warning("ONLINE_POLICY_FALLBACK: policy save failed: %s", type(exc).__name__)

        observation["eligible"] = True
        observation["trainable"] = True
        observation["train_status"] = "APPLIED"
        observation["zero_reason"] = None
        try:
            repo.save_online_observation(observation)
        except Exception as exc:
            if "UNIQUE" in str(exc).upper() or "unique" in str(exc).lower():
                return {
                    **observation,
                    "eligible": False,
                    "duplicate_observation_skipped": True,
                    "zero_reason": "duplicate_observation_skipped",
                    "train_status": "SKIPPED",
                }
            raise
        return observation
    except Exception as exc:  # noqa: BLE001
        logger.warning("ONLINE_POLICY_FALLBACK: observe failed: %s", type(exc).__name__)
        return None
