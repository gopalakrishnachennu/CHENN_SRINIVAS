# PHASE 2.8 GATE 1.1 REPORT — Shadow Evaluation Hardening

**Status:** PASS  
**Starting commit:** `2fe8e1a5aa1c48e44a05da2ba43d8343f7b663b0`  
**Ending commit:** `c0a202ac00bee1c6f6ad3bf738ad9b4a8a061a89`  
**Branch:** `main`  
**Mode:** `shadow` (active production reordering **OFF**)  
**CI:** https://github.com/gopalakrishnachennu/CHENN_SRINIVAS/actions/runs/35820340513

Baseline: [`docs/PHASE_2_8_GATE_1_1_BASELINE.md`](PHASE_2_8_GATE_1_1_BASELINE.md)

---

## Metrics

| Metric | Baseline | Final |
|--------|----------|-------|
| Offline tests | 598 pass / 3 skip | **636** pass / **3** skip |
| Online-learning tests | 29 | **67** (29 Gate1 + 38 Gate1.1) |
| Coverage | 75.09% | **75.50%** |
| Ruff | 0 | **0** |
| GitHub 3.11 | — | **SUCCESS** |
| GitHub 3.12 | — | **SUCCESS** |

---

## Designs

### Decision → observation linkage
One SQLite decision row **per production variant** (`run_id` + `variant_id`).  
`ShadowDecision.decision_id` returned from `save_online_decision`.  
`observe_final_outcome` looks up by `(run_id, variant_id, policy_version)` and stores `decision_id` + `linkage_status`.

### Idempotency / uniqueness
Application check via `has_applied_online_observation` before training.  
Partial unique index on `(run_id, variant_id, policy_version) WHERE train_status='APPLIED'`.  
Duplicate calls return `duplicate_observation_skipped` without re-training.

### Persistence consistency
Order: validate → idempotency → `River.observe` → save policy → save observation `APPLIED`.  
If policy save fails after in-memory observe, observation is still marked APPLIED to prevent double-training; policy file may lag until next successful save.

### River compatibility
Private `_bayes_lin_regs` access isolated in `RiverLinUCBCompat` only.  
Version guard `SUPPORTED_RIVER_VERSION=0.26.1`; incompatible metadata → fallback without deleting original (optional archive copy).

### Fallback actions
`list_all_candidate_positionings()` = eligible + deterministic fallback labels.  
Shadow ranks this set so sparse JD production actions are never rejected as “outside eligible”.

### Evaluator
`build_shadow_evaluation()` reads SQLite rewards as stored (no recompute).  
`activation_ready` always **false** in Gate 1.1 even if sample thresholds would pass.

### Replay diagnostics
Dry-run reports `eligible_records` / `usable_records` / `skipped_records` with `skip_reasons`; policy bytes unchanged.

---

## Files created
- `resume_engine/learning/online/river_compat.py`
- `resume_engine/learning/online/evaluator.py`
- `tests/test_phase28_gate1_1.py`
- `docs/PHASE_2_8_GATE_1_1_BASELINE.md`
- `docs/PHASE_2_8_GATE_1_1_REPORT.md`

## Files modified
- online: `config`, `schemas`, `shadow_runner`, `river_policy`, `policy_store`, `replay`, `reward_engine`
- `variant_planner.py` (`list_all_candidate_positionings`)
- `repository.py` (indexes, columns, lookup/idempotency APIs)
- `phase2_pipeline.py` (per-variant decisions + online summary)
- `implementation_audit.py`

---

## Proof table

| Criterion | Result |
|-----------|--------|
| Shadow mode unchanged | PASS |
| Production ordering unchanged | PASS |
| Decision per variant | PASS |
| Observation linked by decision_id | PASS |
| Cross-variant linking prevented | PASS |
| Duplicate observation blocked | PASS |
| Policy trained only once per final | PASS |
| Sparse JD shadow coverage | PASS |
| Fallback action supported | PASS |
| Action invention impossible | PASS |
| Shadow evaluator works | PASS |
| Agreement rate calculated | PASS |
| Agree reward calculated | PASS |
| Disagree reward calculated | PASS |
| Per-action metrics | PASS |
| Per-family metrics | PASS |
| Insufficient evidence detection | PASS |
| River version compatibility | PASS |
| Feature schema compatibility | PASS |
| Incompatible policy fallback | PASS |
| Replay dry-run immutable | PASS |
| Offline pytest | PASS |
| Coverage ≥70 | PASS |
| Ruff | PASS |
| GitHub Python 3.11 | PASS |
| GitHub Python 3.12 | PASS |
| Active production mode | **OFF** |

---

## Known limitations
1. Active production reordering remains disabled.
2. Evaluator evidence readiness never flips active mode.
3. Policy save failure after in-memory observe relies on APPLIED marker to avoid double-train (file may lag).
4. Do not fabricate 50 observations in tests for activation.
5. Real shadow performance must come from future production runs (not fabricated).

---

# PHASE 2.8 ONLINE LEARNING GATE 1.1 STATUS: PASS
