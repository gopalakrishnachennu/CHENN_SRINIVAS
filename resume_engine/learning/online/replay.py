"""Offline replay of historical SQLite outcomes into River (explicit CLI only)."""

from __future__ import annotations

import argparse
import logging
from typing import Any

from resume_engine.learning.online.config import ONLINE_POLICY_VERSION
from resume_engine.learning.online.feature_builder import build_context_features
from resume_engine.learning.online.reward_engine import compute_reward, is_online_trainable
from resume_engine.learning.online.river_policy import RiverStrategyPolicy
from resume_engine.learning.online.schemas import ReplayReport
from resume_engine.models.jd_blueprint import JDBlueprint

logger = logging.getLogger(__name__)


def _context_from_record(record: dict[str, Any]) -> dict[str, float] | None:
    required = ("primary_family", "secondary_family", "seniority")
    if any(record.get(key) in (None, "") for key in required):
        return None
    blueprint_payload = record.get("blueprint") or record.get("blueprint_snapshot")
    if isinstance(blueprint_payload, dict):
        try:
            blueprint = JDBlueprint.model_validate(blueprint_payload)
            return build_context_features(blueprint)
        except Exception:  # noqa: BLE001
            return None
    try:
        from resume_engine.learning.eligibility import is_hybrid_blueprint
        from resume_engine.learning.online.feature_builder import (
            PRIMARY_FAMILIES,
            SECONDARY_FAMILIES,
            SENIORITIES,
            _one_hot,
        )

        features: dict[str, float] = {}
        features.update(_one_hot("primary_family", str(record["primary_family"]), PRIMARY_FAMILIES))
        features.update(
            _one_hot(
                "secondary_family",
                str(record.get("secondary_family") or "none"),
                SECONDARY_FAMILIES,
            )
        )
        features.update(_one_hot("seniority", str(record["seniority"]), SENIORITIES))
        hybrid = is_hybrid_blueprint(
            record.get("secondary_family"),
            record.get("hybrid_probability"),
        )
        features["hybrid_probability"] = float(
            record.get("hybrid_probability") or (1.0 if hybrid else 0.0)
        )
        features["is_hybrid"] = 1.0 if hybrid else 0.0
        if record.get("p1_count") is None and record.get("priority_skills") is None:
            return None
        return features
    except Exception:  # noqa: BLE001
        return None


def replay_from_repository(
    *,
    dry_run: bool = True,
    limit: int = 5000,
    policy: RiverStrategyPolicy | None = None,
) -> ReplayReport:
    from resume_engine.learning.repository import get_default_repository

    repo = get_default_repository()
    records = repo.get_strategy_history(eligible_only=False, limit=limit)

    eligible = 0
    usable = 0
    skipped = 0
    skip_reasons: dict[str, int] = {}
    action_counts: dict[str, int] = {}
    rewards: list[float] = []
    pol = policy or RiverStrategyPolicy()

    def bump(reason: str) -> None:
        nonlocal skipped
        skipped += 1
        skip_reasons[reason] = skip_reasons.get(reason, 0) + 1

    for record in records:
        if not is_online_trainable(record):
            bump("ineligible")
            continue
        eligible += 1
        action = record.get("variant_positioning")
        if not action:
            bump("missing_action")
            continue
        context = _context_from_record(record)
        if context is None:
            bump("missing_context")
            continue
        reward_result = compute_reward(record)
        if not reward_result.trainable:
            bump("reward_not_trainable")
            continue
        usable += 1
        action_counts[str(action)] = action_counts.get(str(action), 0) + 1
        rewards.append(reward_result.reward)
        if not dry_run:
            pol.observe(context, str(action), reward_result.reward)

    if not dry_run and usable:
        pol.save()

    mean_reward = sum(rewards) / len(rewards) if rewards else None
    return ReplayReport(
        eligible_records=eligible,
        usable_records=usable,
        skipped_records=skipped,
        action_counts=action_counts,
        mean_reward=mean_reward,
        policy_version=ONLINE_POLICY_VERSION,
        dry_run=dry_run,
        skip_reasons=skip_reasons,
        details={"observation_count_after": pol.observation_count if not dry_run else 0},
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay historical outcomes into River policy")
    parser.add_argument("--dry-run", action="store_true", help="Evaluate without mutating policy")
    parser.add_argument("--train", action="store_true", help="Update and persist policy")
    parser.add_argument("--limit", type=int, default=5000)
    args = parser.parse_args(argv)
    if args.train and args.dry_run:
        parser.error("Use either --dry-run or --train, not both")
    dry = not args.train
    report = replay_from_repository(dry_run=dry, limit=args.limit)
    print(report.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
