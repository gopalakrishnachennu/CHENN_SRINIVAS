"""Shadow-performance analytics for River online learning (Gate 1.1)."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from resume_engine.config.settings import REPORT_STORAGE_DIR, ensure_storage_dirs
from resume_engine.learning.online.config import (
    ONLINE_MIN_ACTION_OBSERVATIONS,
    ONLINE_MIN_TOTAL_OBSERVATIONS,
    ONLINE_POLICY_VERSION,
)
from resume_engine.learning.online.schemas import ShadowEvaluation


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def build_shadow_evaluation(
    *,
    policy_version: str | None = ONLINE_POLICY_VERSION,
    limit: int = 10000,
) -> ShadowEvaluation:
    """
    Evaluate shadow decisions vs stored final rewards from SQLite.

    Does not recompute rewards. Does not modify policy.
    """
    from resume_engine.learning.repository import get_default_repository

    repo = get_default_repository()
    decisions = repo.list_online_decisions(limit=limit)
    observations = repo.list_online_observations(limit=limit)

    if policy_version:
        decisions = [d for d in decisions if d.get("policy_version") == policy_version]
        observations = [o for o in observations if o.get("policy_version") == policy_version]

    decision_by_id = {int(d["id"]): d for d in decisions if d.get("id") is not None}
    linked = [o for o in observations if o.get("decision_id") is not None]
    unlinked = [o for o in observations if o.get("decision_id") is None]
    eligible_obs = [
        o for o in observations if int(o.get("eligible") or 0) == 1 or o.get("train_status") == "APPLIED"
    ]

    agree_rewards: list[float] = []
    disagree_rewards: list[float] = []
    all_rewards: list[float] = []
    agree_count = 0
    disagree_count = 0

    per_action: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "production_count": 0,
            "shadow_top_count": 0,
            "observation_count": 0,
            "rewards": [],
        }
    )
    per_family: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"observation_count": 0, "rewards": [], "agree": 0, "total": 0}
    )

    multi_action = 0
    single_action = 0
    for decision in decisions:
        available = []
        try:
            available = json.loads(decision.get("available_actions_json") or "[]")
        except (TypeError, json.JSONDecodeError):
            available = []
        if len(available) <= 1:
            single_action += 1
        else:
            multi_action += 1

        prod = decision.get("production_action") or ""
        top = decision.get("shadow_top_action") or ""
        if prod:
            per_action[prod]["production_count"] += 1
        if top:
            per_action[top]["shadow_top_count"] += 1

        agrees = bool(int(decision.get("shadow_agrees") or 0))
        if agrees:
            agree_count += 1
        else:
            disagree_count += 1

    for obs in observations:
        reward = float(obs.get("reward") or 0.0)
        all_rewards.append(reward)
        action = obs.get("action") or ""
        if action:
            per_action[action]["observation_count"] += 1
            per_action[action]["rewards"].append(reward)

        decision = decision_by_id.get(int(obs["decision_id"])) if obs.get("decision_id") is not None else None
        family = "unknown"
        if decision:
            try:
                ctx = json.loads(decision.get("context_json") or "{}")
            except (TypeError, json.JSONDecodeError):
                ctx = {}
            for key, value in ctx.items():
                if key.startswith("primary_family_") and float(value or 0) == 1.0:
                    family = key.replace("primary_family_", "", 1)
                    break
            agrees = bool(int(decision.get("shadow_agrees") or 0))
            per_family[family]["total"] += 1
            if agrees:
                per_family[family]["agree"] += 1
                agree_rewards.append(reward)
            else:
                disagree_rewards.append(reward)
        per_family[family]["observation_count"] += 1
        per_family[family]["rewards"].append(reward)

    total_decisions = len(decisions)
    agreement_rate = (
        agree_count / total_decisions if total_decisions else None
    )

    per_action_out = {
        action: {
            "production_count": stats["production_count"],
            "shadow_top_count": stats["shadow_top_count"],
            "observation_count": stats["observation_count"],
            "mean_reward": _mean(stats["rewards"]),
        }
        for action, stats in sorted(per_action.items())
    }
    per_family_out = {
        family: {
            "observation_count": stats["observation_count"],
            "mean_reward": _mean(stats["rewards"]),
            "shadow_agreement_rate": (
                stats["agree"] / stats["total"] if stats["total"] else None
            ),
        }
        for family, stats in sorted(per_family.items())
    }

    timestamps = [d.get("created_at") for d in decisions if d.get("created_at")]
    timestamps += [o.get("created_at") for o in observations if o.get("created_at")]
    timestamps = sorted(t for t in timestamps if t)

    action_counts = {
        action: stats["observation_count"]
        for action, stats in per_action_out.items()
        if stats["observation_count"] > 0
    }
    insufficient = len(eligible_obs) < ONLINE_MIN_TOTAL_OBSERVATIONS
    evidence_ready = (
        len(eligible_obs) >= ONLINE_MIN_TOTAL_OBSERVATIONS
        and bool(action_counts)
        and all(c >= ONLINE_MIN_ACTION_OBSERVATIONS for c in action_counts.values())
    )
    # Gate 1.1: analytics may report evidence readiness, but must not enable active mode.
    activation_ready = False

    return ShadowEvaluation(
        total_decisions=total_decisions,
        linked_observations=len(linked),
        eligible_observations=len(eligible_obs),
        unlinked_observations=len(unlinked),
        shadow_agreement_count=agree_count,
        shadow_disagreement_count=disagree_count,
        shadow_agreement_rate=agreement_rate,
        mean_reward_all=_mean(all_rewards),
        mean_reward_when_shadow_agrees=_mean(agree_rewards),
        mean_reward_when_shadow_disagrees=_mean(disagree_rewards),
        multi_action_decisions=multi_action,
        single_action_decisions=single_action,
        per_action=per_action_out,
        per_primary_family=per_family_out,
        policy_coverage={
            "contexts_seen": len({d.get("jd_hash") for d in decisions}),
            "distinct_actions_seen": len(per_action_out),
            "eligible_actions_seen": len(
                {
                    a
                    for d in decisions
                    for a in (
                        json.loads(d.get("available_actions_json") or "[]")
                        if isinstance(d.get("available_actions_json"), str)
                        else []
                    )
                }
            ),
        },
        policy_version=policy_version,
        date_range={
            "start": timestamps[0] if timestamps else None,
            "end": timestamps[-1] if timestamps else None,
        },
        insufficient_evidence=insufficient,
        activation_ready=activation_ready,
        details={
            "evidence_ready_but_gate_keeps_shadow": evidence_ready,
            "required_observations": ONLINE_MIN_TOTAL_OBSERVATIONS,
            "required_per_action": ONLINE_MIN_ACTION_OBSERVATIONS,
        },
    )


def write_evaluation_report(evaluation: ShadowEvaluation) -> Path:
    ensure_storage_dirs()
    out_dir = REPORT_STORAGE_DIR / "online"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / f"shadow_evaluation_{stamp}.json"
    path.write_text(evaluation.model_dump_json(indent=2), encoding="utf-8")
    return path


def _print_human(evaluation: ShadowEvaluation) -> None:
    print(f"Policy: {evaluation.policy_version}")
    print("Mode: shadow")
    print()
    print(f"Total decisions: {evaluation.total_decisions}")
    print(f"Linked outcomes: {evaluation.linked_observations}")
    print(f"Eligible outcomes: {evaluation.eligible_observations}")
    print(f"Unlinked outcomes: {evaluation.unlinked_observations}")
    print()
    rate = evaluation.shadow_agreement_rate
    print(f"Agreement rate: {rate if rate is not None else 'n/a'}")
    print()
    print(f"Mean reward overall: {evaluation.mean_reward_all}")
    print(f"Mean reward when shadow agrees: {evaluation.mean_reward_when_shadow_agrees}")
    print(f"Mean reward when shadow disagrees: {evaluation.mean_reward_when_shadow_disagrees}")
    print()
    print(f"Observations required: {ONLINE_MIN_TOTAL_OBSERVATIONS}")
    print(f"Current observations: {evaluation.eligible_observations}")
    print("Activation evidence ready: NO")
    if evaluation.insufficient_evidence:
        print("INSUFFICIENT_SHADOW_EVIDENCE")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Shadow online-learning evaluation")
    parser.add_argument("--policy-version", default=ONLINE_POLICY_VERSION)
    parser.add_argument("--write-report", action="store_true")
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args(argv)
    evaluation = build_shadow_evaluation(policy_version=args.policy_version)
    if args.write_report:
        path = write_evaluation_report(evaluation)
        print(f"Wrote report: {path}")
    if args.json_only or not args.write_report:
        print(evaluation.model_dump_json(indent=2))
    if not args.json_only:
        _print_human(evaluation)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
