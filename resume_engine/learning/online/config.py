"""Online learning configuration (Phase 2.8).

Default mode is shadow — River observes but never changes production selection.
"""

from __future__ import annotations

import os
from typing import Literal

from resume_engine.config.settings import load_local_environment

OnlineMode = Literal["disabled", "shadow", "active"]

ONLINE_LEARNING_ENABLED = True
ONLINE_LEARNING_MODE: OnlineMode = "shadow"

ONLINE_POLICY_VERSION = "river-linucb-v1"
ONLINE_POLICY_SEED = 42
FEATURE_SCHEMA_VERSION = "online-features-v1"

ONLINE_MIN_TOTAL_OBSERVATIONS = 50
ONLINE_MIN_ACTION_OBSERVATIONS = 5

ONLINE_MAX_REWARD = 1.0
ONLINE_MIN_REWARD = 0.0

# Reserved for a later activation gate — Phase 2.8 must not enable active.
ONLINE_ACTIVE_WEIGHT_MAX = 0.20

ALLOWED_MODES = frozenset({"disabled", "shadow", "active"})


def get_online_learning_mode() -> OnlineMode:
    load_local_environment()
    raw = (os.getenv("RESUME_ONLINE_LEARNING_MODE") or ONLINE_LEARNING_MODE).strip().lower()
    if raw not in ALLOWED_MODES:
        return "shadow"
    # Phase 2.8 Gate 1: never silently run active without evidence gate elsewhere.
    if raw == "active":
        # Fall back unless an explicit later gate enables active with evidence.
        # For this phase, always treat configured active as shadow-safe fallback
        # when evidence thresholds are unmet (checked by callers).
        return "active"
    return raw  # type: ignore[return-value]


def online_learning_enabled() -> bool:
    if not ONLINE_LEARNING_ENABLED:
        return False
    return get_online_learning_mode() != "disabled"


def get_policy_seed() -> int:
    load_local_environment()
    raw = (os.getenv("RESUME_ONLINE_POLICY_SEED") or str(ONLINE_POLICY_SEED)).strip()
    try:
        return int(raw)
    except ValueError:
        return ONLINE_POLICY_SEED


def evidence_allows_active(*, observation_count: int, action_counts: dict[str, int]) -> bool:
    if observation_count < ONLINE_MIN_TOTAL_OBSERVATIONS:
        return False
    if not action_counts:
        return False
    return all(count >= ONLINE_MIN_ACTION_OBSERVATIONS for count in action_counts.values())
