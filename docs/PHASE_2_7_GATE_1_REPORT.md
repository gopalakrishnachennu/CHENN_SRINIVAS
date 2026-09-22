# PHASE 2.7 GATE 1 REPORT — Critical Correctness

**Status:** `PHASE 2.7 GATE 1 STATUS: PASS`  
**Report written (UTC):** 2026-09-22T15:18:00Z  
**Starting commit:** `4e27d5b43c5a4c56c1404c2eee3b78a063d2cacc`  
**Ending commit:** still `4e27d5b43c5a4c56c1404c2eee3b78a063d2cacc` (working tree dirty; Gate 1 not committed)  
**Branch:** `main`

Baseline capture: [`docs/PHASE_2_7_GATE_1_BASELINE.md`](PHASE_2_7_GATE_1_BASELINE.md)

---

## 1–3. Starting state

| Item | Value |
|------|-------|
| Exact starting commit | `4e27d5b43c5a4c56c1404c2eee3b78a063d2cacc` |
| Pre-existing modified files before Gate 1 | **none** (clean tree at baseline) |
| Ending working-tree state | dirty with Gate 1 edits (see §29–31) |
| Python | 3.12.6 |

---

## 4–9. Metrics: baseline → final

| Metric | Baseline | Final |
|--------|----------|-------|
| `pytest -q` | collected 471; **467** passed; **0** failed; **4** skipped | collected 532; **528** passed; **0** failed; **4** skipped |
| `pytest -m "not live"` | **467** passed; **3** skipped; **1** deselected | **528** passed; **3** skipped; **1** deselected |
| Ruff (`python3 -m ruff check resume_engine tests`) | **9** errors (historical) | **7** errors (historical only; Gate 1 introduced none) |
| Coverage (`not live`) | **73.14%** (`coverage_gate1_baseline.json`) | **73.04%** (`coverage_gate1_final.json`) |
| Behavioral audit | PASS | **PASS** |
| Implementation audit | Importable 42/42 (`tested=false` on import) | Importable **42/42** |
| Live OpenAI/Laya | LIVE_TEST_NOT_RUN | **LIVE_TEST_NOT_RUN** |

Gate 1 targeted suite: `tests/test_phase27_gate1.py` → **61 passed**.  
Wave suite (`wave1/2/3/4` + `phase3_export`): **90 passed**.  
No previously passing offline test regressed.

---

## 10–13. P4 semantics

### Previous behavior
Hard gate used **available-P4 ratio**: `used_p4 / available_p4`.  
Pathological: 1 available + 1 used → 100% FAIL; 2 available + 1 used → 50% FAIL.

### New behavior
Hard gate uses **share of used priority skills** plus a **one-P4 floor**:

```text
used_required = unique detected P1 + P2 + P3
used_p4       = unique detected P4
priority_skill_total = len(used_required) + len(used_p4)
p4_share = len(used_p4) / max(1, priority_skill_total)

PASS when:
  used_p4_count == 0
  OR used_p4_count == 1          # one_p4_floor_applied
  OR p4_share <= P4_USAGE_MAX    # 0.35
```

`available_p4_ratio` remains **diagnostic only** (also aliased as `usage_ratio` for backward compatibility).

Missing P4 never fails coverage and never enters required repair / `APPEND_SKILL`.

### Examples

| Case | Result |
|------|--------|
| 1 P4 available, 1 used | PASS (floor) |
| 2 P4 available, 1 used | PASS (floor); available ratio 0.5 diagnostic |
| 3 P4 available, 1 used | PASS (floor) |
| Larger set, many P4 + few required so share > 0.35 | FAIL_P4_OVERUSE |

---

## 14–19. Repair operations

### Schema
Typed `RepairOperation` with legacy `{location, replacement}` coerced to `REPLACE_TEXT`.

### Supported operations
- `REPLACE_TEXT`
- `REPLACE_SKILL`
- `APPEND_SKILL`
- `REMOVE_SKILL`
- `REPLACE_EXPERIENCE_BULLET`
- `APPEND_EXPERIENCE_BULLET`
- `REPLACE_PROJECT_BULLET`

Python applies patches; LLM may only supply text. Technologies must be in `blueprint.generation_contract.allowed_technologies` or raise `FAIL_REPAIR_UNAPPROVED_TECHNOLOGY`.

### Missing P1 / P2
`FAIL_P1_COVERAGE` / `FAIL_P2_COVERAGE` → deterministic `APPEND_SKILL` into existing group or `"Core Technologies"`.

### TEMPLATE mode
May append blueprint-allowed skills for required coverage.

### CANDIDATE mode
Only appends skills verified in candidate evidence. Otherwise records `UNRESOLVED_REQUIRED_CANDIDATE_GAP` and keeps variant from validated final.

---

## 20–21. Per-variant failure isolation

`process_variant` catches ordinary `Exception` (not `KeyboardInterrupt` / `SystemExit`), writes `reports/<VID>_pipeline_error.json`, returns:

```json
{
  "variant_id": "V03",
  "passed": false,
  "status": "PIPELINE_ERROR",
  "final_resume": null,
  "eligible_for_learning": false
}
```

Other variants continue. Failed variants never enter `validated/`.

---

## 22–24. run_id + collision

- Regex: `^[A-Za-z0-9_-]{1,64}$`
- Rejects: `../`, `/`, `\`, `.`, `..`, empty, whitespace-only, length > 64 → `InvalidRunIdError` (no silent sanitize)
- Collision: `mkdir(..., exist_ok=False)` → `RunAlreadyExistsError`
- Metadata / strategy / artifacts refuse overwrite (`FileExistsError`)

---

## 25–27. Learning lifecycle

### Before
Successful attempt could save learning immediately; regeneration could save again → multiple eligible successes for same `run_id + variant_id`.

### After
1. Attempts run with `persist_learning=False`; records marked `is_final_selection=false`, `eligible_for_learning=false`
2. Superseded duplicates marked `superseded=true` (diagnostic save only)
3. After regen settles, **one** final outcome per variant with `is_final_selection=true`
4. Eligibility requires: `passed` + `is_final_selection` + not `superseded` + quality gates + not `PIPELINE_ERROR`

Proof: Gate 1 tests `test_initial_success_then_regenerated_success_counts_once`, `test_superseded_attempt_not_eligible`, `test_one_run_variant_has_at_most_one_eligible_final_outcome`.

---

## 28. Report / artifact versioning

Attempt-scoped paths:

- `raw/<VID>_attempt_NN_raw.json`
- `repaired/<VID>_attempt_NN_repair.json`
- `reports/<VID>/attempt_NN/{before_repair,after_repair,final,rejected}_validation.{json,txt}`
- `validated/<VID>_attempt_NN_final.json` + first `V01_final.json`; regen writes marker `V01_final_selected_attempt.json` without overwriting prior attempt files

Invariant: no silent overwrite of prior attempt evidence.

---

## 29–31. Files

### Created
- `docs/PHASE_2_7_GATE_1_BASELINE.md`
- `docs/PHASE_2_7_GATE_1_REPORT.md` (this file)
- `tests/test_phase27_gate1.py`
- `coverage_gate1_baseline.json`
- `coverage_gate1_final.json`

### Modified
| File | Why |
|------|-----|
| `resume_engine/validation/p4_usage_validator.py` | Share-of-used + one-P4 floor |
| `resume_engine/scoring/score_engine.py` | Score using share/floor |
| `resume_engine/reports/behavioral_audit.py` | Audit uses `p4_within_policy` |
| `resume_engine/repair/patch_applier.py` | Typed ops + tech guard |
| `resume_engine/repair/repair_planner.py` | Executable ops + candidate gaps |
| `resume_engine/repair/repair_validator.py` | Pass mode/profile/resume into planner |
| `resume_engine/repair/targeted_rewriter.py` | Deterministic skill ops; LLM text only |
| `resume_engine/storage/run_store.py` | run_id validation, collision, attempt artifacts, pipeline error reports |
| `resume_engine/pipeline/phase2_pipeline.py` | Isolation, deferred learning, attempt metadata |
| `resume_engine/learning/eligibility.py` | Final/superseded/PIPELINE_ERROR gates |
| `tests/test_wave1_p0.py` | Align P4 + artifact name expectations |
| `resume_engine/storage/reports/BEHAVIORAL_AUDIT.json` | Regenerated audit evidence |

### Deleted
None.

---

## 32–35. Tests / regressions

### New tests (`tests/test_phase27_gate1.py`)
All required Gate 1 names plus `test_missing_p2_produces_executable_append_skill` and parametrized dangerous run_id coverage.

### Existing tests changed
- `tests/test_wave1_p0.py`: P4 asserts use floor/share details; artifact filenames updated to attempt-scoped names; removed unused `PROJECT_ROOT` import.

### Regressions found / fixed
- Wave1 P4 tests expected old available-ratio gate → updated to new semantics.
- Wave1 artifact name asserts expected `V01_raw.json` → updated to `V01_attempt_01_raw.json`.
- Learning eligibility circular `eligible_for_learning=False` blocked final eligibility → clear flag before recompute in settle/persist paths.
- Ruff unused imports introduced by Gate 1 → removed.

---

## 36. DISCOVERED_NOT_FIXED_GATE1

1. Historical Ruff unused imports (repository, ui/app, wave2/wave3, behavioral fixture `plan`) — Gate 3.
2. Coverage ~73% with no enforced threshold — Gate 3/4 diagnostic policy.
3. Cross-run MinHash/SimHash redesign — later gate.
4. Responsibility / Laya `[:8]` semantic redesign — later gate.
5. SQLite as sole learning SoT — later gate.
6. DOCX/PDF/UI polish — out of scope.
7. Phase 1 live E2E — LIVE_TEST_NOT_RUN.
8. After regen, stable `V01_final.json` retains attempt-01 bytes; selection is via `V01_final_selected_attempt.json` (consumers must prefer marker) — acceptable Gate 1; broader pointer sync deferred.
9. Dual-write learning may still persist superseded diagnostics into JSONL/SQLite (correctly ineligible) — ranking contamination blocked; storage hygiene polishing deferred.

---

## 37. Live tests

| Item | Result |
|------|--------|
| Live OpenAI generation E2E | LIVE_TEST_NOT_RUN |
| Live Laya E2E | LIVE_TEST_NOT_RUN |
| Paid API spend | not performed |

---

## MANDATORY GATE 1 PROOF TABLE

| Criterion | Result | Evidence |
|-----------|--------|----------|
| P4 zero usage | PASS | `test_p4_zero_used_passes` |
| P4 single approved adjacent skill | PASS | `test_single_available_single_used_passes` |
| P4 over-dominance | PASS | `test_multiple_p4_can_fail_when_adjacent_share_dominates`, `test_p4_overuse_still_fails` |
| P4 remains optional | PASS | `test_p4_missing_never_becomes_required`, `test_p4_missing_never_enters_missing_skills` |
| Missing P1 produces executable repair | PASS | `test_template_mode_can_append_blueprint_allowed_skill` |
| Missing P2 produces executable repair | PASS | `test_missing_p2_produces_executable_append_skill` |
| Candidate-mode unsupported skill is not invented | PASS | `test_candidate_mode_cannot_invent_missing_skill` |
| Unapproved repair technology blocked | PASS | `test_append_skill_rejects_unapproved_technology` |
| One variant repair failure does not kill run | PASS | `test_repair_failure_in_one_variant_does_not_stop_others`, `test_other_variants_continue_after_error` |
| Failed variant never reaches validated/ | PASS | `test_pipeline_error_variant_never_becomes_final` |
| Dangerous run_id rejected | PASS | `test_run_id_rejects_*` |
| Duplicate run_id cannot overwrite run | PASS | `test_existing_run_id_is_rejected`, `test_existing_run_metadata_cannot_be_overwritten` |
| Raw attempt preserved | PASS | `test_regeneration_does_not_overwrite_raw_resume` |
| Repair attempt preserved | PASS | `test_regeneration_does_not_overwrite_repair_resume` |
| Validation reports preserved across regeneration | PASS | `test_attempt_01_and_attempt_02_reports_both_exist` |
| Superseded variant excluded from learning | PASS | `test_superseded_attempt_not_eligible` |
| Only final accepted variant eligible for learning | PASS | `test_one_run_variant_has_at_most_one_eligible_final_outcome` |
| Existing Phase 2.6 behavioral audit | PASS | `python3 -m resume_engine.reports.behavioral_audit` → PASS |
| Full offline pytest | PASS | **528** passed, **3** skipped, **0** failed (`not live`) |

---

## PASS CRITERIA CHECK

- [x] no failing non-live tests
- [x] no previously passing test regressed
- [x] P4 small-set bug fixed; P4 remains optional
- [x] required P1/P2 repair has executable operations
- [x] candidate mode does not invent unsupported facts
- [x] repair cannot introduce unapproved technology
- [x] variant-specific errors isolated; failed never validated
- [x] run_id traversal blocked; run collision blocked
- [x] previous artifacts not silently overwritten
- [x] regenerated attempts cannot contaminate learning
- [x] only final accepted variant eligible learning success
- [x] regeneration reports remain inspectable
- [x] existing behavioral audit still passes

---

# PHASE 2.7 GATE 1 STATUS: PASS

Do **not** begin Gate 2 from this report alone. Production readiness requires Gates 1–4 independently verified.
