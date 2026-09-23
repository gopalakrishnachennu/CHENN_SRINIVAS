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
    context_version: str
    policy_version: str
    mode: str
    available_actions: list[str] = Field(default_factory=list)
    production_action: str
    production_order: list[str] = Field(default_factory=list)
    shadow_ranked_actions: list[PolicyPrediction] = Field(default_factory=list)
    shadow_top_action: str | None = None
    shadow_agrees_with_production: bool = False
    created_at: str
    context: dict[str, float] = Field(default_factory=dict)
    fallback_reason: str | None = None


class RewardResult(BaseModel):
    reward: float
    components: dict[str, float] = Field(default_factory=dict)
    trainable: bool = False
    zero_reason: str | None = None


class ReplayReport(BaseModel):
    eligible_records: int = 0
    usable_records: int = 0
    skipped_records: int = 0
    action_counts: dict[str, int] = Field(default_factory=dict)
    mean_reward: float | None = None
    policy_version: str
    dry_run: bool = True
    details: dict[str, Any] = Field(default_factory=dict)
