"""Schemas for online policy predictions, shadow decisions, and rewards."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PolicyPrediction(BaseModel):
    action: str
    rank: int
    score: float | None = None
    probability: float | None = None  # null unless calibrated probs exist
    policy_version: str
    model_observation_count: int = 0


class ShadowDecision(BaseModel):
    run_id: str
    jd_hash: str
    variant_id: str | None = None
    decision_id: int | None = None
    context_version: str
    policy_version: str
    mode: str
    available_actions: list[str] = Field(default_factory=list)
    production_action: str
    production_rank: int | None = None
    production_order: list[str] = Field(default_factory=list)
    shadow_ranked_actions: list[PolicyPrediction] = Field(default_factory=list)
    shadow_top_action: str | None = None
    shadow_rank_of_production_action: int | None = None
    shadow_agrees_with_production: bool = False
    observation_count_at_prediction: int = 0
    created_at: str
    context: dict[str, float] = Field(default_factory=dict)
    fallback_reason: str | None = None


class RewardResult(BaseModel):
    reward: float
    components: dict[str, float] = Field(default_factory=dict)
    trainable: bool = False
    zero_reason: str | None = None
    reward_schema_version: str = "reward-v1"


class ReplayReport(BaseModel):
    eligible_records: int = 0
    usable_records: int = 0
    skipped_records: int = 0
    action_counts: dict[str, int] = Field(default_factory=dict)
    mean_reward: float | None = None
    policy_version: str
    dry_run: bool = True
    skip_reasons: dict[str, int] = Field(default_factory=dict)
    details: dict[str, Any] = Field(default_factory=dict)


class ShadowEvaluation(BaseModel):
    total_decisions: int = 0
    linked_observations: int = 0
    eligible_observations: int = 0
    unlinked_observations: int = 0
    shadow_agreement_count: int = 0
    shadow_disagreement_count: int = 0
    shadow_agreement_rate: float | None = None
    mean_reward_all: float | None = None
    mean_reward_when_shadow_agrees: float | None = None
    mean_reward_when_shadow_disagrees: float | None = None
    multi_action_decisions: int = 0
    single_action_decisions: int = 0
    per_action: dict[str, dict[str, Any]] = Field(default_factory=dict)
    per_primary_family: dict[str, dict[str, Any]] = Field(default_factory=dict)
    policy_coverage: dict[str, Any] = Field(default_factory=dict)
    policy_version: str | None = None
    date_range: dict[str, str | None] = Field(default_factory=dict)
    insufficient_evidence: bool = True
    activation_ready: bool = False
    details: dict[str, Any] = Field(default_factory=dict)
