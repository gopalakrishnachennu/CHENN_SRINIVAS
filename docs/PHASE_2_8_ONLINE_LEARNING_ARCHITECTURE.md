# Phase 2.8 — Online Self-Learning Architecture

## Purpose

Add a **River** contextual bandit layer that learns from final validated outcomes
while keeping the existing deterministic / historical strategy engine authoritative.

Phase 2.8 Gate 1 runs exclusively in **shadow mode**.

## Two learning systems

| Layer | Role | Authoritative? |
|-------|------|----------------|
| Historical SQLite + `strategy_memory` | Eligible outcomes boost angle ranking after min samples | **Yes** (production) |
| River LinUCB (`river-linucb-v1`) | Observes context/action/reward; ranks same eligible angles | **No** (shadow only) |

River does **not** replace SQLite history, OpenAI/Laya, or validation thresholds.

## Flow

```
JD Blueprint
  → deterministic variant planner (eligible angles)
  → historical ranking → PRODUCTION variants
  → River shadow ranks same eligible actions
  → shadow decision persisted (SQLite)
  → normal Phase 2 pipeline unchanged
  → final validated selection
  → reward engine (bounded [0,1])
  → River.observe() only if trainable
  → policy.pkl persisted atomically
```

## Concepts

- **Context**: deterministic blueprint features (`feature_builder.py`), no candidate PII
- **Action**: `variant_positioning` from eligible planner set only (no invention)
- **Reward**: multi-metric validated score with hard zeros for firewall/P1/fail/superseded
- **Observation**: only `is_final_selection` + eligible learning records
- **Policy**: `RiverStrategyPolicy` adapter over `river.bandit.LinUCBDisjoint`
- **Shadow mode**: compare River top vs production top; never reorder variants
- **Activation gate**: later phase; requires observation thresholds; Gate 1 keeps shadow

## Configuration

```bash
RESUME_ONLINE_LEARNING_MODE=shadow   # disabled | shadow | active
RESUME_ONLINE_POLICY_SEED=42
```

Default: **shadow**. Active is not enabled for production selection in Gate 1.

## Persistence

- Policy: `resume_engine/storage/learning/online/policy.pkl` (+ `.previous.pkl`)
- Metadata: `policy_metadata.json`
- Decisions / observations: SQLite tables on existing LearningRepository DB

## Replay

Explicit CLI only (never at app startup):

```bash
python3 -m resume_engine.learning.online.replay --dry-run
python3 -m resume_engine.learning.online.replay --train
```

Incomplete historical context is skipped (never fabricated).

## Invariants

1. `river_action ∈ eligible_variant_positionings`
2. Technology firewall remains authoritative (learner cannot add tech)
3. Online failures → `ONLINE_POLICY_FALLBACK` → deterministic continues
4. Label after Gate 1: `ONLINE_LEARNING_SHADOW_VALIDATED` (not production-active)
