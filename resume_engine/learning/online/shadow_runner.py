"""Shadow-mode online learning: observe rankings without changing production."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from resume_engine.learning.online.config import (
    FEATURE_SCHEMA_VERSION,
    ONLINE_POLICY_VERSION,
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

# Re-export for tests
__all__ = [
    "observe_final_outcome",
    "record_shadow_decision",
    "reset_default_policy_for_tests",
]


def _eligible_actions(blueprint: JDBlueprint) -> list[str]:
    from resume_engine.strategy.variant_planner import list_eligible_positionings

    return list_eligible_positionings(blueprint)


def effective_mode(*, policy: RiverStrategyPolicy | None = None) -> str:
    mode = get_online_learning_mode()
    if mode != "active":
        return mode
    pol = policy or get_default_policy()
    if evidence_allows_active(
        observation_count=pol.observation_count,
        action_counts=pol.action_counts,
    ):
        # Still Phase 2.8 Gate 1: do not activate production reordering.
        logger.warning(
            "ONLINE_POLICY_FALLBACK: active requested but Gate 1 keeps shadow selection"
        )
    return "shadow"


def record_shadow_decision(
    *,
    blueprint: JDBlueprint,
    production_order: list[str],
    run_id: str,
    variant_id: str | None = None,
    policy: RiverStrategyPolicy | None = None,
) -> ShadowDecision | None:
    """
    Rank eligible actions with River and persist a shadow decision.

    Never mutates production_order. On any failure, logs and returns None.
    """
    if not online_learning_enabled():
        return None

    mode = effective_mode(policy=policy)
    if mode == "disabled":
        return None

    try:
        eligible = _eligible_actions(blueprint)
        if not eligible:
            return None
        # Production actions must be subset of eligible.
        if not set(production_order).issubset(set(eligible)):
            logger.warning(
                "ONLINE_POLICY_FALLBACK: production actions outside eligible set"
            )
            return None

        context = build_context_features(blueprint)
        assert_no_pii(context)

        pol = policy or get_default_policy()
        ranked = pol.rank_actions(context, eligible)
        assert {p.action for p in ranked}.issubset(set(eligible))

        production_action = production_order[0] if production_order else eligible[0]
        shadow_top = ranked[0].action if ranked else None
        decision = ShadowDecision(
            run_id=run_id,
            jd_hash=blueprint.jd_hash,
            variant_id=variant_id,
            context_version=FEATURE_SCHEMA_VERSION,
            policy_version=getattr(pol, "policy_version", ONLINE_POLICY_VERSION),
            mode=mode,
            available_actions=list(eligible),
            production_action=production_action,
            production_order=list(production_order),
            shadow_ranked_actions=ranked,
            shadow_top_action=shadow_top,
            shadow_agrees_with_production=bool(shadow_top == production_action),
            created_at=datetime.now(UTC).isoformat(),
            context=context,
        )

        from resume_engine.learning.repository import get_default_repository

        get_default_repository().save_online_decision(decision.model_dump(mode="json"))
        return decision
    except Exception as exc:  # noqa: BLE001 — never break Phase 2
        logger.warning("ONLINE_POLICY_FALLBACK: shadow decision failed: %s", type(exc).__name__)
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

    Returns observation summary or None when skipped / failed soft.
    """
    if not online_learning_enabled():
        return None

    try:
        reward_result = compute_reward(learning_record)
        action = learning_record.get("variant_positioning")
        if not action:
            return None

        from resume_engine.learning.repository import get_default_repository

        repo = get_default_repository()
        observation = {
            "run_id": learning_record.get("run_id"),
            "jd_hash": learning_record.get("jd_hash"),
            "variant_id": learning_record.get("variant_id"),
            "action": action,
            "reward": reward_result.reward,
            "reward_components": reward_result.components,
            "eligible": reward_result.trainable,
            "zero_reason": reward_result.zero_reason,
            "policy_version": ONLINE_POLICY_VERSION,
        }

        if not reward_result.trainable:
            repo.save_online_observation(observation)
            return observation

        if blueprint is None:
            # Cannot update without context features.
            observation["eligible"] = False
            observation["zero_reason"] = "missing_blueprint_context"
            repo.save_online_observation(observation)
            return observation

        context = build_context_features(blueprint)
        assert_no_pii(context)
        eligible = set(_eligible_actions(blueprint))
        if action not in eligible:
            observation["eligible"] = False
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

        repo.save_online_observation(observation)
        return observation
    except Exception as exc:  # noqa: BLE001
        logger.warning("ONLINE_POLICY_FALLBACK: observe failed: %s", type(exc).__name__)
        return None
