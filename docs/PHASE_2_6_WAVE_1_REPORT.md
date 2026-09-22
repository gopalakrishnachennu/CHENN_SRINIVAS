# PHASE 2.6 — WAVE 1 COMPLETION REPORT

**Date:** 2026-09-22  
**Scope:** P0 Correctness only (P4, failed-final gate, score regression, immutable artifacts, run_id, patch repair)  
**Wave 0 audit:** accepted; not redone  
**Wave 2+:** not started

---

## 1. Baseline test numbers (before Wave 1 code changes)

| Metric | Value |
|--------|-------|
| Collected | 377 |
| Passed | 374 |
| Failed | 0 |
| Skipped | 3 |

Skip reasons (unchanged): all for fixture `12_sparse_poor_jd` (insufficient P1 / family=`other`).

---

## 2. Files modified

- `resume_engine/config/settings.py` — `RUNS_STORAGE_DIR`, `REJECTED_STORAGE_DIR`, `PROMPT_VERSION`, `portable_path()`
- `resume_engine/validation/coverage_validator.py` — skip P4 / `technical_skills_optional` required-placement failures
- `resume_engine/strategy/strategy_builder.py` — `p4_limits` reads `thresholds.P4_USAGE_MAX`
- `resume_engine/repair/repair_planner.py` — blueprint-aware; P4 excluded from `missing_skills`; `targets` list
- `resume_engine/repair/repair_validator.py` — passes blueprint into planner
- `resume_engine/repair/targeted_rewriter.py` — requests `RepairPatchResponse` only; Python applies patches
- `resume_engine/pipeline/phase2_pipeline.py` — run_id, run store, p4 validator, gate, regression selection, portable paths
- `resume_engine/main.py` — optional `--run-id`
- `resume_engine/reports/behavioral_audit.py` — real P4 threshold + Wave 1 invariant proofs; good resume ≤ P4 max
- `tests/fixture_resume_builder.py` — good resumes include P4 only within `P4_USAGE_MAX` (corrects prior stuffing)

---

## 3. Files created

- `resume_engine/validation/p4_usage_validator.py`
- `resume_engine/repair/patch_applier.py`
- `resume_engine/repair/version_selector.py`
- `resume_engine/storage/__init__.py`
- `resume_engine/storage/run_store.py`
- `tests/test_wave1_p0.py` (29 new tests)
- `docs/PHASE_2_6_WAVE_1_REPORT.md` (this file)

---

## 4. Files deleted

None.

---

## 5. Exact P4 changes

| Change | Detail |
|--------|--------|
| SoT | `thresholds.P4_USAGE_MAX` only (no duplicated hardcode in strategy/audit) |
| New validator | `validate_p4_usage` → empty P4 ⇒ ratio 0 PASS; else PASS iff `usage_ratio <= max`; else `FAIL_P4_OVERUSE` |
| Pipeline | Added to `run_validators` after coverage |
| Coverage | P4 entities and `technical_skills_optional` never emit `FAIL_MISSING_REQUIRED_PLACEMENT` |
| Repair | Missing P4 never enters `missing_skills` |
| Behavioral audit | Compares against `thresholds.P4_USAGE_MAX` (was `<= 1.0`) |
| Fixtures | Good resumes no longer include all P4 skills |

Proven audit: `usage_ratio=0.25`, `max_ratio=0.35`, validator PASS.

---

## 6. Exact final-pass gate changes

`process_variant` now:

1. Saves RAW under run `raw/`
2. Optionally repairs → `repaired/`
3. Selects version via `select_best_resume_version`
4. **Only if** `status == VALIDATED` → write `validated/<variant>_final.json`
5. Else → write `rejected/<variant>_rejected.json`, set:
   - `passed: false`
   - `status: FAILED_VALIDATION`
   - `final_resume: null`
   - `rejected_resume: <portable path>`

Invariant: failed resume cannot enter `validated/`.

---

## 7. Repair score regression logic

`select_best_resume_version`:

1. Passing beats failing
2. Both pass → higher score wins
3. Both fail → `FAILED_VALIDATION` (no validated promotion)
4. If `score_after < score_before` → record `REPAIR_SCORE_REGRESSION`

Covered by test using historical case **86.59 → 86.57**.

---

## 8. Artifact versioning changes

Under `resume_engine/storage/runs/<jd_hash>/<run_id>/`:

| Stage | Name |
|-------|------|
| Raw | `raw/V01_raw.json` |
| Repair | `repaired/V01_repair_01.json` (increments) |
| Final | `validated/V01_final.json` |
| Rejected | `rejected/V01_rejected.json` |

Overwrite of an existing artifact path raises `FileExistsError`.  
Legacy flat `generated/` / `validated/` writers remain in tree for old artifacts but the live pipeline writes run-scoped paths.

---

## 9. Run ID architecture

- Auto UUID4 if `--run-id` omitted
- Optional CLI `--run-id`
- Layout: `storage/runs/<jd_hash>/<run_id>/{metadata.json,strategy,raw,repaired,validated,rejected,reports}`
- `metadata.json` includes run_id, jd_hash, generation_mode, created_at, variant_count, model, blueprint_version, prompt_version
- Persisted result paths use `portable_path()` (project-relative)
- Learning outcomes include `run_id` when written by the pipeline

---

## 10. Targeted patch design

1. LLM returns `RepairPatchResponse` (`patches[{location, replacement}]`) only
2. `apply_resume_patches` deep-copies resume, validates locations, applies only allowed plan targets
3. Mutation guard compares non-target fields → `FAIL_REPAIR_SCOPE_VIOLATION`
4. Invalid / out-of-scope locations → `FAIL_INVALID_PATCH_LOCATION` / `FAIL_OUT_OF_SCOPE_PATCH`

**Live OpenAI end-to-end patch call:** `LIVE_TEST_NOT_RUN` (unit tests mock/apply patches deterministically).

---

## 11. New test names (`tests/test_wave1_p0.py`)

**P4:**  
`test_zero_p4_usage_passes`, `test_p4_below_limit_passes`, `test_p4_exact_limit_passes`, `test_p4_above_limit_fails`, `test_missing_p4_does_not_trigger_required_placement`, `test_missing_p4_does_not_enter_repair_missing_skills`, `test_repair_does_not_stuff_p4`

**Final gate:**  
`test_failed_resume_not_saved_to_validated`, `test_passed_resume_saved_to_validated`, `test_failed_resume_saved_to_rejected`

**Regression:**  
`test_repair_score_regression_detected`, `test_better_valid_version_selected`, `test_failed_versions_never_promoted`

**Artifacts / run isolation:**  
`test_raw_artifact_preserved`, `test_repair_artifact_is_separate`, `test_final_artifact_is_separate`, `test_artifact_paths_do_not_overwrite`, `test_run_id_generated`, `test_same_jd_two_runs_do_not_collide`, `test_run_id_in_metadata`, `test_run_id_in_learning_record_if_learning_is_written`, `test_persisted_paths_are_portable`

**Patch repair:**  
`test_patch_changes_only_targeted_bullet`, `test_non_target_summary_unchanged`, `test_non_target_skills_unchanged`, `test_non_target_experience_unchanged`, `test_invalid_patch_path_rejected`, `test_out_of_scope_patch_rejected`, `test_repair_scope_violation_detected`

---

## 12–15. Total tests after change

| Metric | After Wave 1 |
|--------|----------------|
| Collected | **406** |
| Passed | **403** |
| Failed | **0** |
| Skipped | **3** |

Delta vs baseline: +29 new Wave 1 tests; no regressions of previously passing tests.  
Fixture builder P4 limit change was an intentional correction of incorrect “stuff all P4” behavior; existing behavioral fixtures still pass.

---

## 16. Behavioral audit result

```text
RESULT: PASS
phase: Phase 2.6 Wave 1

[PASS] P1 coverage
[PASS] P2 coverage
[PASS] P4 limit respected          (0.25 <= 0.35)
[PASS] P4 optional semantics
[PASS] Failed-final gate
[PASS] Raw artifact preserved
[PASS] Run isolation
[PASS] Targeted repair
[PASS] Repair scope guard
```

---

## 17. Backward compatibility result

- `python3 phase_2_resume_pipeline.py --blueprint … --variants 5` still works
- `--run-id` optional (auto UUID)
- Existing offline fixture pytest suite still green
- Legacy flat strategy write retained alongside run-scoped strategy artifact

---

## 18. Unresolved issues (deferred — not Wave 1)

- Live OpenAI patch-repair E2E not executed (`LIVE_TEST_NOT_RUN`)
- Implementation audit still equates import with `tested=true` (Wave 2)
- Learning still does not influence strategy ranking (Wave 3)
- Variant catalog still fixed cloud/Databricks/DevOps/AI (Wave 2)
- Laya still first-20 bullets (Wave 2)
- Certifications still `list[str]` (Wave 2)
- No bullet-level provenance (Wave 2)
- No cross-run fingerprint uniqueness (Wave 2)
- No SQLite / central LLM client / CI / gitignore privacy hardening (Wave 4)
- Committed historical flat storage artifacts untouched (by design)

---

## 19. Explicit Wave 2 items NOT implemented

1. Dynamic family-aware variant planner  
2. CertificationRequirement schema  
3. Bullet-level provenance / ResumeBullet  
4. Responsibility ID mapping (R001…) beyond keyword overlap  
5. Full Laya batching  
6. Cross-variant auto regeneration of weaker duplicates  
7. Cross-run uniqueness fingerprints  
8. Implementation audit honesty redesign  
9. Score calibration / variant_focus_score marketing rename work beyond existing internal label  
10. Self-learning strategy retrieval (Wave 3)  
11. SQLite LearningRepository (Wave 4)  
12. Central LLM client (Wave 4)  
13. CI / pyproject (Wave 4)  
14. DOCX / PDF / UI (Phase 3 — forbidden)

---

## Invariant proof checklist

```text
P4 skills aren't forced into resumes                 ✓
Failed resume cannot become final                    ✓
86.59 → 86.57 repair does NOT become accepted        ✓
raw generation survives repair                       ✓
same JD + run A / run B don't overwrite each other   ✓
one bad bullet → only that bullet changes            ✓
```

---

```text
WAVE 1 STATUS: PASS
```

**STOP.** Do not begin Wave 2 until explicitly instructed.
