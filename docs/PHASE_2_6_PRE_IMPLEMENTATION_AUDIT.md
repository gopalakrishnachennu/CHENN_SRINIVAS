# PHASE 2.6 PRE-IMPLEMENTATION AUDIT

**Status:** ANALYSIS ONLY — no functional source code modified.  
**Date:** 2026-09-22  
**Repo:** `gopalakrishnachennu/CHENN_SRINIVAS`  
**Method:** Full tree listing; every `resume_engine/**/*.py` opened; Phase 1/2 entrypoints, thresholds, tests, fixtures, committed storage artifacts, learning JSONL, and import/call traces inspected. Conclusions marked IMPLEMENTED / PARTIALLY_IMPLEMENTED / BROKEN / NOT_IMPLEMENTED / NOT_PROVEN.

---

## A. Repository metrics

| Metric | Value (proven) |
|--------|----------------|
| Total `.py` files (excl. venv/cache) | 62 |
| `resume_engine/` Python modules | 54 files / ~2816 LOC |
| `tests/` Python modules | 5 files / ~1245 LOC |
| Root Phase engines | `jd_blueprint_engine.py` (771 LOC), `phase_1_jd_intelligence_blueprint.py` (97), `phase_2_resume_pipeline.py` (23) |
| Fixture JD texts | 15 under `tests/fixtures/jds/` |
| Fixture assertion files | `fixture_assertions.json`, `hybrid_devops_databricks_ai.json` |
| Pytest collected | **377** tests (all in `tests/test_behavioral_fixtures.py`; deterministic fixtures; no live OpenAI/Laya) |
| Committed generated resumes | 6 under `resume_engine/storage/generated/` |
| Committed validated artifacts | 8 under `resume_engine/storage/validated/` |
| Committed reports | 22 under `resume_engine/storage/reports/` |
| Learning outcomes JSONL | 7 lines |
| Learning failures JSONL | 5 lines |
| `docs/` before this audit | absent |
| CI workflow | absent |
| `pyproject.toml` / `requirements-dev.txt` | absent |
| `resume_engine/llm/` | absent |
| `p4_usage_validator.py` | **absent** |
| SQLite learning DB | absent |
| `.gitignore` runtime exclusions for `storage/` | **absent** (only `.env`, `resume_engine_data/`, caches) |

---

## B. Architecture map

```
JD text
  → phase_1_jd_intelligence_blueprint.py / jd_blueprint_engine.py
      extract_jd (OpenAI) → registry update → Laya hybrid/priority/adjacent
      → JD_BLUEPRINT.json (resume_engine_data/blueprints/<jd_hash>.json)

JD_BLUEPRINT
  → resume_engine.main / phase_2_resume_pipeline
      → strategy_builder.build_strategy
      → variant_planner.create_variants (fixed V01–V05)
      → openai_generator.generate_resume_with_openai
      → provenance.attach_skill_provenance
      → save_generated_resume (storage/generated/<jd_hash>_<variant>_resume.json)
      → run_validators (ordered list below)
      → score_engine.calculate_score
      → repair_validator.should_repair / repair_planner.build_repair_plan
      → targeted_rewriter.rewrite_targeted_resume_parts (full OpenAIResumeJSON)
      → save_generated_resume AGAIN (same filename — overwrite)
      → save_validated_resume ALWAYS (storage/validated/…)
      → outcome_store / failure_store / pattern_updater (JSONL summary only)
      → variant_similarity_validator (detect only; no regen)
```

**Package layout (recognizable Phase 2):**

- `config/` — settings paths, thresholds
- `strategy/` — builder, variants, placement, role positioning
- `generation/` — prompts, OpenAI client, provenance, save
- `validation/` — firewall, coverage, AI placement, responsibility, hybrid, Laya, duplicate, role drift, ATS, variant similarity
- `scoring/` — weighted INTERNAL optimization score
- `repair/` — plan, should_repair, rewriter
- `learning/` — JSONL outcomes/failures + summary file
- `reports/` — validation reports, behavioral audit, implementation audit
- `pipeline/` — `phase2_pipeline.py` orchestration
- `models/` — blueprint, resume, strategy, validation schemas

---

## C. Entrypoints

| Entry | Role |
|-------|------|
| `python3 phase_1_jd_intelligence_blueprint.py` | Paste JD → Phase 1 blueprint |
| `python3 jd_blueprint_engine.py --jd-file …` | CLI Phase 1 |
| `python3 phase_2_resume_pipeline.py --blueprint …` | Delegates to `resume_engine.main` |
| `python3 -m resume_engine.main` | Phase 2 CLI (`--blueprint`, `--variants`, `--no-repair`, `--skip-laya`, audits) |
| `python3 -m resume_engine.reports.behavioral_audit` | Offline monster-JD behavioral checks |
| `python3 -m resume_engine.reports.implementation_audit` | Import-presence audit |
| `pytest` / `--run-fixture-tests` | 377 deterministic behavioral tests |

**CLI gaps vs Phase 2.6:** no `--run-id`; no rejected-output path; no live-test marker.

---

## D. Data flow

1. Blueprint loaded via `JDBlueprint.from_json_file`.
2. Generation context: TEMPLATE (`resume_seed.json`) or CANDIDATE (`candidate_profile`).
3. Strategy written to `storage/strategies/strategy_<jd_hash>.json`.
4. Each variant → OpenAI structured `OpenAIResumeJSON` → `ResumeJSON` + skill provenance.
5. Artifacts keyed primarily by **`jd_hash` + `variant_id`** (no `run_id`).
6. Summary written to `storage/validated/<jd_hash>_phase2_summary.json` with **absolute machine paths**.

---

## E. Validation flow (`run_validators`)

Order in `phase2_pipeline.run_validators`:

1. `validate_blueprint_ready`
2. `validate_technology_firewall`
3. `validate_coverage`
4. `validate_ai_tool_placement`
5. `validate_responsibilities`
6. `validate_hybrid_family_retention`
7. `validate_duplicates`
8. `validate_role_drift`
9. `validate_ats`
10. `validate_with_laya` (if agent present; **bullets[:20] only**)

Post-batch (pipeline end only): `validate_variant_similarity` — detection only.

**Pass rule:** no `severity=="error"` issues AND `optimization_score >= PASS_SCORE_MIN` (92.0).

**Missing from chain:** `p4_usage_validator` (file does not exist). Strategy stores `p4_limits.max_optional_mentions_ratio: 0.35` but no validator reads it for hard fail.

---

## F. Repair flow

1. `should_repair`: repair if not (passed AND score≥92) when score≥88 OR not passed.
2. `build_repair_plan`: aggregates missing skills from coverage / placement / AI codes; **does not exclude P4**.
3. `rewrite_targeted_resume_parts`: prompts model to “Repair only failing areas” but **requires complete OpenAIResumeJSON**; Python does not apply patches; no mutation guard.
4. Repaired resume saved via `save_generated_resume` → **same path as raw**.
5. Revalidate; then **always** `save_validated_resume` regardless of `passed`.

---

## G. Learning flow

1. `save_learning_outcome` appends JSONL with scores, failures, `successful_pattern=final_bundle.passed`.
2. Failures also go to `failures.jsonl` when `failures` list non-empty — including **passed** runs that still have warning-coded `FAIL_MISSING_REQUIRED_PLACEMENT` for P4/optional skills.
3. `update_learning_patterns` → `summarize_strategy_memory` averages scores by `(primary, secondary, variant_positioning)`.
4. **`build_strategy` / `create_variants` never read strategy memory.** Learning is write-only / summary-only.

---

## H. Existing tests

| Layer | Status |
|-------|--------|
| Behavioral fixture suite | IMPLEMENTED — 377 collected tests, offline |
| Unit tests for P4 usage / failed-final / patch repair / run_id | NOT_IMPLEMENTED |
| Phase 1 offline extraction unit layer | NOT_IMPLEMENTED (fixtures synthesize blueprints via `fixture_blueprint_builder.py`, not Phase 1 engine) |
| Live `RUN_LIVE_TESTS=1` Phase 1 E2E | NOT_IMPLEMENTED |
| Markers (`unit`/`integration`/`behavioral`/`live`) | NOT_IMPLEMENTED |
| Test tree layout (`tests/unit|integration|…`) | NOT_IMPLEMENTED |

**Proven test coverage:** firewall, coverage P1, AI placement, hybrid, duplicates, ATS, repair *plan* presence, variant similarity detection — against **hand-built** blueprints/resumes.  
**Not proven by tests:** live OpenAI generation, live Laya, real patch locality, failed-final gate, P4 max ratio, learning feedback into strategy.

---

## I. Existing runtime outputs (committed)

| Artifact | Evidence |
|----------|----------|
| `6e60d4d225581288` 5-variant TEMPLATE run | All `passed=true` in summary; validated finals present; absolute `/Users/...` paths |
| `3b63a75c28b6c7e2` 1-variant run | `passed=false`, scores 86.59→86.57, **still saved** `…/validated/3b63a75c28b6c7e2_V01final_final_resume.json` |
| Repair overwrite | V02: `generated_resume` and `repaired_resume` are **identical path** `…_V02_resume.json` |
| BEHAVIORAL_AUDIT | `p4_usage.usage_ratio=1.0` yet `"P4 limit respected": true` |
| Implementation audit | Every imported module marked `tested: true` |
| Outcomes | V01 6e60… `successful_pattern: true` while failures list contains many `FAIL_MISSING_REQUIRED_PLACEMENT` (P4/optional warnings) |

---

## J. Confirmed defects

### ISSUE_ID: P26-P4-001
- **FILE:** `resume_engine/reports/behavioral_audit.py`
- **FUNCTION:** `run_behavioral_audit` (`pass_conditions["P4 limit respected"]`)
- **CURRENT_BEHAVIOR:** `p4_usage_ratio <= 1.0` hard-coded.
- **EXPECTED_BEHAVIOR:** Compare against `thresholds.P4_USAGE_MAX` (0.35) / strategy `p4_limits`.
- **EVIDENCE:** Line 390: `p4_usage_ratio <= 1.0`; committed audit shows `usage_ratio: 1.0` and PASS; `thresholds.P4_USAGE_MAX = 0.35`.
- **RISK:** Audit reports PASS with 100% P4 usage.
- **PROPOSED_FIX:** Import `thresholds.P4_USAGE_MAX`; never duplicate 0.35.
- **TEST_REQUIRED:** Behavioral/unit assert use of configured max; fixture with ratio 1.0 must FAIL audit condition.
- **CLASSIFICATION:** BROKEN

### ISSUE_ID: P26-P4-002
- **FILE:** (missing) `resume_engine/validation/p4_usage_validator.py`
- **FUNCTION:** N/A
- **CURRENT_BEHAVIOR:** No module; not in `run_validators`.
- **EXPECTED_BEHAVIOR:** Compute `p4_total_available/used/usage_ratio`; empty P4 → ratio 0 PASS; else PASS iff `usage_ratio <= P4_USAGE_MAX`; issue `FAIL_P4_OVERUSE`.
- **EVIDENCE:** `ls resume_engine/validation/` has no `p4_usage_validator.py`; grep finds no `FAIL_P4_OVERUSE`.
- **RISK:** Over-stuffed optional skills never hard-fail.
- **PROPOSED_FIX:** Create validator; wire into `run_validators`; single threshold source.
- **TEST_REQUIRED:** `test_zero_p4_usage_passes`, below/exact/above limit.
- **CLASSIFICATION:** NOT_IMPLEMENTED

### ISSUE_ID: P26-P4-003
- **FILE:** `resume_engine/validation/coverage_validator.py`
- **FUNCTION:** `validate_coverage` placement loop
- **CURRENT_BEHAVIOR:** For every entity placement including P4 `technical_skills_optional`, missing skill emits `FAIL_MISSING_REQUIRED_PLACEMENT` (severity warning for non-P1/P2).
- **EXPECTED_BEHAVIOR:** P4 / `technical_skills_optional` absence must **never** create `FAIL_MISSING_REQUIRED_PLACEMENT`; optional means allowed, not required.
- **EVIDENCE:** Runtime `6e60…_V01before_repair_validation.json` lines 59–89: PySpark/Delta Lake/Unity Catalog missing `technical_skills_optional` as `FAIL_MISSING_REQUIRED_PLACEMENT` warnings. Reproduced offline: zero-P4 resume still gets four P4 placement warnings.
- **RISK:** Pollutes reports/learning; drives repair stuffing.
- **PROPOSED_FIX:** Skip optional placements / P4 entities in required-placement enforcement.
- **TEST_REQUIRED:** `test_missing_p4_does_not_create_repair` / no FAIL_MISSING for P4.
- **CLASSIFICATION:** BROKEN

### ISSUE_ID: P26-P4-004
- **FILE:** `resume_engine/repair/repair_planner.py`
- **FUNCTION:** `build_repair_plan`
- **CURRENT_BEHAVIOR:** Any `FAIL_MISSING_REQUIRED_PLACEMENT` appends skill to `missing_skills` regardless of priority/placement optionality.
- **EXPECTED_BEHAVIOR:** Missing P4 must not populate `missing_skills`; never stuff optional skills unless another hard failure explicitly requires it within P4 limit.
- **EVIDENCE:** Offline reproduction with zero-P4 resume: `missing_skills` includes Delta Lake, PySpark, Docker, Helm. Behavioral audit repair plan also lists those P4 skills.
- **RISK:** Repair prompt asks model to add optional skills.
- **PROPOSED_FIX:** Filter by priority≠P4 and placement≠`technical_skills_optional`; consult blueprint.
- **TEST_REQUIRED:** `test_repair_does_not_stuff_optional_skills`
- **CLASSIFICATION:** BROKEN

### ISSUE_ID: P26-P4-005
- **FILE:** `resume_engine/strategy/strategy_builder.py`
- **FUNCTION:** `build_strategy`
- **CURRENT_BEHAVIOR:** Writes `p4_limits.max_optional_mentions_ratio: 0.35` literal; threshold also in `thresholds.py`.
- **EXPECTED_BEHAVIOR:** Single source of truth from `thresholds.P4_USAGE_MAX`.
- **EVIDENCE:** Hardcoded `0.35` in strategy_builder line 44; duplicate of thresholds.
- **RISK:** Drift between strategy metadata and enforcement.
- **PROPOSED_FIX:** Read `thresholds.P4_USAGE_MAX`.
- **TEST_REQUIRED:** Assert strategy limit equals thresholds constant.
- **CLASSIFICATION:** PARTIALLY_IMPLEMENTED (limit stored, unused for validation)

### ISSUE_ID: P26-GATE-001
- **FILE:** `resume_engine/pipeline/phase2_pipeline.py`
- **FUNCTION:** `process_variant` → `save_validated_resume`
- **CURRENT_BEHAVIOR:** Always saves `{resume_id}_final_resume.json` under `validated/` even when `final_bundle.passed` is false.
- **EXPECTED_BEHAVIOR:** Only `passed==True` enters validated final; failures → rejected store; result `status=FAILED_VALIDATION`, `final_resume=null`, `rejected_resume=path`.
- **EVIDENCE:** `3b63…_phase2_summary.json`: `"passed": false` and `"final_resume": "…/validated/3b63…_V01final_final_resume.json"`; file exists on disk.
- **RISK:** Failed resumes treated as production finals.
- **PROPOSED_FIX:** Gate save; add rejected directory; status fields.
- **TEST_REQUIRED:** `test_failed_resume_never_saved_to_validated`, `test_successful_resume_saved_to_validated`, `test_failed_repair_goes_to_rejected`
- **CLASSIFICATION:** BROKEN

### ISSUE_ID: P26-GATE-002
- **FILE:** `resume_engine/pipeline/phase2_pipeline.py`
- **FUNCTION:** `process_variant` repair accept path
- **CURRENT_BEHAVIOR:** Always accepts repaired resume; no check that `score_after >= score_before`; 3b63 run shows 86.59 → 86.57 accepted.
- **EXPECTED_BEHAVIOR:** Record `REPAIR_SCORE_REGRESSION`; keep both versions; prefer version that passes hard gates with better valid score; if both fail → reject/regenerate/review.
- **EVIDENCE:** Summary score_before 86.59 / score_after 86.57 / passed false / still validated path.
- **RISK:** Silent quality regression.
- **PROPOSED_FIX:** Compare scores; retain RAW vs REPAIRED; choose/reject policy.
- **TEST_REQUIRED:** `test_repair_score_regression_recorded`
- **CLASSIFICATION:** NOT_IMPLEMENTED

### ISSUE_ID: P26-ART-001
- **FILE:** `resume_engine/generation/resume_generator.py`
- **FUNCTION:** `save_generated_resume`
- **CURRENT_BEHAVIOR:** Fixed name `{jd_hash}_{variant_id}_resume.json`; repair overwrites raw.
- **EXPECTED_BEHAVIOR:** Immutable stage names e.g. `V01_raw.json`, `V01_repair_01.json`, `V01_final.json` under run tree.
- **EVIDENCE:** V02 summary: generated and repaired paths identical; 3b63 same.
- **RISK:** Loss of initial generation forensics.
- **PROPOSED_FIX:** Stage-aware artifact writer with unique paths + metadata.
- **TEST_REQUIRED:** `test_raw_resume_preserved_after_repair`, `test_repair_creates_new_artifact`, `test_artifact_paths_unique`
- **CLASSIFICATION:** BROKEN

### ISSUE_ID: P26-RUN-001
- **FILE:** `resume_engine/pipeline/phase2_pipeline.py`, `config/settings.py`
- **FUNCTION:** storage layout / `run_phase2_pipeline`
- **CURRENT_BEHAVIOR:** Namespace is `jd_hash` only under flat `generated/`, `validated/`, `reports/`.
- **EXPECTED_BEHAVIOR:** `storage/runs/<jd_hash>/<run_id>/{strategy,raw,repaired,validated,rejected,reports,metadata.json}` with UUID4 run_id; optional `--run-id`.
- **EVIDENCE:** No `run_id` in code/grep; settings only define flat dirs.
- **RISK:** Multi-customer same-JD collisions / overwrite.
- **PROPOSED_FIX:** Generate run_id; nested storage; backward-compatible CLI.
- **TEST_REQUIRED:** `test_same_jd_two_runs_have_different_paths`, propagation tests
- **CLASSIFICATION:** NOT_IMPLEMENTED

### ISSUE_ID: P26-REP-001
- **FILE:** `resume_engine/repair/targeted_rewriter.py`
- **FUNCTION:** `rewrite_targeted_resume_parts`
- **CURRENT_BEHAVIOR:** LLM returns full resume JSON; no stable IDs; no Python patch apply; no scope guard.
- **EXPECTED_BEHAVIOR:** Patch schema only; deepcopy + deterministic apply; `FAIL_REPAIR_SCOPE_VIOLATION` if non-targets change.
- **EVIDENCE:** System prompt: “Return the complete repaired OpenAIResumeJSON”; no patch types in models.
- **RISK:** Untargeted drift; false “targeted repair” claims.
- **PROPOSED_FIX:** Stable IDs, patch plan, apply_patches, mutation guard.
- **TEST_REQUIRED:** only-target / summary unchanged / invalid location / out-of-scope
- **CLASSIFICATION:** PARTIALLY_IMPLEMENTED (intent in prompt; mechanism absent)

### ISSUE_ID: P26-PATH-001
- **FILE:** `phase2_pipeline.py`, learning updater, summaries
- **FUNCTION:** result serialization
- **CURRENT_BEHAVIOR:** Persists absolute paths `/Users/gopalakrishnachennu/Desktop/CHENN_SRINIVAS/...`
- **EXPECTED_BEHAVIOR:** Relative/logical IDs e.g. `runs/<jd_hash>/<run_id>/raw/V01.json`
- **EVIDENCE:** Both phase2 summaries and BEHAVIORAL_AUDIT assertion path contain `/Users/…`
- **RISK:** Non-portable; leaks machine layout.
- **PROPOSED_FIX:** Relative to PROJECT_ROOT or artifact IDs.
- **TEST_REQUIRED:** Cross-OS relative path assertions
- **CLASSIFICATION:** BROKEN

### ISSUE_ID: P26-LEARN-001
- **FILE:** `learning/strategy_memory.py`, `strategy/strategy_builder.py`, `strategy/variant_planner.py`
- **FUNCTION:** summarize vs build
- **CURRENT_BEHAVIOR:** Memory summary written; never consumed by strategy/variants.
- **EXPECTED_BEHAVIOR:** Retrieve eligible successful history by family/hybrid/seniority; apply ranking only if `count >= LEARNING_MIN_SAMPLE_COUNT`; never learn failures; never introduce tech outside blueprint.
- **EVIDENCE:** No imports of strategy_memory into strategy_builder/variant_planner; pattern_updater only saves summary.
- **RISK:** “Self-learning” is storage theater.
- **PROPOSED_FIX:** Retrieval API + eligibility gates + ranking hook.
- **TEST_REQUIRED:** failed not used; insufficient history noop; success changes ranking; family scope; no new tech
- **CLASSIFICATION:** PARTIALLY_IMPLEMENTED (persist) / NOT_IMPLEMENTED (feedback)

### ISSUE_ID: P26-AUDIT-001
- **FILE:** `reports/implementation_audit.py`
- **FUNCTION:** `run_implementation_audit`
- **CURRENT_BEHAVIOR:** `tested=True` on successful `importlib.import_module`.
- **EXPECTED_BEHAVIOR:** Fields: exists, imports, unit_test_exists/passed, integration_*, live_test_status — never equate import with tested.
- **EVIDENCE:** Lines 48–51 set `tested=True` with details `Imported …`
- **RISK:** False implementation confidence.
- **PROPOSED_FIX:** Replace schema + probe pytest collection/results where possible.
- **TEST_REQUIRED:** Audit fixture asserting import≠tested
- **CLASSIFICATION:** BROKEN

### ISSUE_ID: P26-LAYA-001
- **FILE:** `validation/laya_validator.py`
- **FUNCTION:** `validate_with_laya`
- **CURRENT_BEHAVIOR:** `limited_bullets = bullets[:20]`; single predict call; failure path not retry/classify.
- **EXPECTED_BEHAVIOR:** Batch all bullets (`LAYA_BULLET_BATCH_SIZE`); retries; failed batch ≠ silent pass.
- **EVIDENCE:** Lines 39–40, 58, details `validated_bullet_count: len(limited_bullets)`
- **RISK:** Bullets after 20 unvalidated.
- **PROPOSED_FIX:** Chunking + aggregate ValidatorResult + failure recording.
- **TEST_REQUIRED:** >20 bullets all validated; batch counts; failed batch not pass
- **CLASSIFICATION:** PARTIALLY_IMPLEMENTED

### ISSUE_ID: P26-VAR-001
- **FILE:** `strategy/variant_planner.py`
- **FUNCTION:** `create_variants` / `VARIANT_DEFINITIONS`
- **CURRENT_BEHAVIOR:** Always five hard-coded angles: cloud / databricks / devops / cloud_data_engineering / ai_enabled_data_platform.
- **EXPECTED_BEHAVIOR:** Family-aware dynamic ranking from blueprint evidence; no unrelated angles (e.g. no databricks_heavy on pure analyst JD without evidence).
- **EVIDENCE:** `VARIANT_DEFINITIONS` constant lines 5–11; no JD family branching for which angles exist.
- **RISK:** Irrelevant variants for non-hybrid/non-data JDs.
- **PROPOSED_FIX:** Angle libraries + evidence gates + keep default count 5 when possible.
- **TEST_REQUIRED:** Per-family variant relevance + hybrid + no unrelated
- **CLASSIFICATION:** PARTIALLY_IMPLEMENTED (emphasis tweaks exist; catalog fixed)

### ISSUE_ID: P26-DIV-001
- **FILE:** `validation/variant_similarity_validator.py`, `pipeline/phase2_pipeline.py`
- **FUNCTION:** similarity validate at end of run
- **CURRENT_BEHAVIOR:** Detects `FAIL_VARIANT_DUPLICATION`; does not regenerate weaker variant.
- **EXPECTED_BEHAVIOR:** Choose weaker by score/focus; regenerate only weaker; `VARIANT_REGEN_MAX=2`; re-check P1/P2/firewall/family/role/P4.
- **EVIDENCE:** Pipeline stores diversity result only; no regen loop.
- **RISK:** Duplicate variants ship.
- **PROPOSED_FIX:** Regeneration controller in pipeline.
- **TEST_REQUIRED:** regenerates weaker only; valid not regen; retry limit
- **CLASSIFICATION:** PARTIALLY_IMPLEMENTED (detect) / NOT_IMPLEMENTED (correct)

### ISSUE_ID: P26-CERT-001
- **FILE:** `models/jd_blueprint.py`, `jd_blueprint_engine.py`, `models/resume_schema.py`
- **FUNCTION:** certifications fields
- **CURRENT_BEHAVIOR:** `list[str]` in extraction, blueprint, and resume; no requirement/evidence/candidate_verified.
- **EXPECTED_BEHAVIOR:** `CertificationRequirement` with mandatory/required/preferred/mentioned; template never claims unverified as earned; candidate mode only verified.
- **EVIDENCE:** `JDBlueprint.certifications: list[str]`; `JDExtraction.certifications: list[str]`; `ResumeJSON.certifications: list[str]`
- **RISK:** Semantic flattening; false possession claims.
- **PROPOSED_FIX:** Structured model + generation/prompt rules + tests.
- **TEST_REQUIRED:** mandatory/preferred preserved; template/candidate claim rules
- **CLASSIFICATION:** NOT_IMPLEMENTED (structured) / PARTIALLY_IMPLEMENTED (strings carried)

### ISSUE_ID: P26-PROV-001
- **FILE:** `models/resume_schema.py`, `generation/provenance.py`
- **FUNCTION:** skill provenance only
- **CURRENT_BEHAVIOR:** Skill-level `SkillProvenance`; bullets are plain `list[str]`.
- **EXPECTED_BEHAVIOR:** Bullet objects with id, technologies, responsibility_ids, provenance; firewall uses bullet.technologies ⊆ allowed.
- **EVIDENCE:** `ResumeExperience.bullets: list[str]`; provenance attaches from technical_skills/certs/projects only.
- **RISK:** Text-only tech detection via finite `KNOWN_TECH_WORDS`.
- **PROPOSED_FIX:** ResumeBullet model + firewall upgrade.
- **TEST_REQUIRED:** unapproved blocked; approved JD tool allowed; LLM tool blocked; provenance survives repair
- **CLASSIFICATION:** PARTIALLY_IMPLEMENTED (skills) / NOT_IMPLEMENTED (bullets)

### ISSUE_ID: P26-RESP-001
- **FILE:** `validation/responsibility_validator.py`
- **FUNCTION:** `validate_responsibilities`
- **CURRENT_BEHAVIOR:** Global keyword overlap on flattened experience text; no R001 IDs; no per-bullet mapping report.
- **EXPECTED_BEHAVIOR:** Stable responsibility IDs; bullet `responsibility_ids`; deterministic overlap + optional Laya; report `R001 -> EXP0_B2 PASS 0.91`.
- **EVIDENCE:** Loop over `blueprint.responsibilities` strings; coverage dict keyed by full string.
- **RISK:** Weak/noisy coverage; hard to repair precisely.
- **PROPOSED_FIX:** ID assignment + mapping + report.
- **TEST_REQUIRED:** Mapping presence for high-priority responsibilities
- **CLASSIFICATION:** PARTIALLY_IMPLEMENTED

### ISSUE_ID: P26-GIT-001
- **FILE:** `.gitignore`
- **CURRENT_BEHAVIOR:** Does not ignore `resume_engine/storage/runs|generated|validated|rejected|learning|reports` or `*.sqlite3`.
- **EXPECTED_BEHAVIOR:** Ignore production runtime outputs; document untracking; do not auto-delete committed samples.
- **EVIDENCE:** `.gitignore` only `.env*`, `resume_engine_data/`, caches; storage artifacts are committed.
- **RISK:** Customer artifacts enter git.
- **PROPOSED_FIX:** Expand gitignore + docs; leave existing fixtures until explicit cleanup.
- **TEST_REQUIRED:** N/A (docs + policy)
- **CLASSIFICATION:** BROKEN (policy)

### ISSUE_ID: P26-FIRE-001
- **FILE:** `validation/technology_firewall.py`
- **FUNCTION:** text scan via `KNOWN_TECH_WORDS`
- **CURRENT_BEHAVIOR:** Finite word list; unknown proper tools in prose may silently pass if not in list and not in structured skills.
- **EXPECTED_BEHAVIOR:** Prefer structured bullet technologies; flag unknown proper tools for inspection rather than invent classification.
- **EVIDENCE:** `KNOWN_TECH_WORDS` set lines 9–40; scan only those terms in summary/experience.
- **RISK:** Novel hallucinated tools evade text scan.
- **PROPOSED_FIX:** Bullet-level tech fields + unknown flag path.
- **TEST_REQUIRED:** With provenance/bullet tech tests
- **CLASSIFICATION:** PARTIALLY_IMPLEMENTED

---

## K. Suspected defects requiring validation

| ID | Suspicion | Why NOT_PROVEN yet |
|----|-----------|-------------------|
| P26-SUS-001 | `passed=true` while learning `failures` lists `FAIL_*` for optional placement confuses eligibility | Need Wave 3 eligibility filter design against warning vs error |
| P26-SUS-002 | Repair may change non-failing sections in live OpenAI runs | No mutation guard; live comparison not run in this audit (`LIVE_TEST_NOT_RUN`) |
| P26-SUS-003 | Score marketed as ATS-like externally via naming confusion | Internal report already says “INTERNAL OPTIMIZATION SCORE” in text report; CLI/README still say “Quality Score” — documentation inconsistency |
| P26-SUS-004 | Cross-run uniqueness absent may already collide in multi-tenant use | No prior fingerprint store; only architectural gap until implemented |
| P26-SUS-005 | Phase 1 fixture blueprints may diverge from live OpenAI/Laya blueprints | Fixtures are hand-authored; live E2E not executed |
| P26-SUS-006 | `should_repair` keeps `action=REPAIR_REQUIRED` after failed repair in 3b63 summary | Need clarify post-repair action mapping vs `FAIL_REGENERATE_OR_REVIEW` |

---

## L. Missing functionality (Phase 2.6 scope)

| Capability | State |
|------------|-------|
| P4 usage validator | NOT_IMPLEMENTED |
| Failed-final / rejected storage | NOT_IMPLEMENTED |
| Immutable raw/repair/final artifacts + metadata | NOT_IMPLEMENTED |
| run_id + runs/ tree | NOT_IMPLEMENTED |
| Patch-based targeted repair + scope guard | NOT_IMPLEMENTED |
| Dynamic family-aware variant planner | NOT_IMPLEMENTED (fixed catalog) |
| Learning → strategy feedback + eligibility + min samples | NOT_IMPLEMENTED |
| Phase 1 offline unit + opt-in live tests | NOT_IMPLEMENTED |
| CertificationRequirement model | NOT_IMPLEMENTED |
| Bullet-level provenance / responsibility IDs | NOT_IMPLEMENTED |
| Full Laya batching | NOT_IMPLEMENTED |
| Cross-variant auto regeneration | NOT_IMPLEMENTED |
| Cross-run fingerprint uniqueness | NOT_IMPLEMENTED |
| Trustworthy implementation audit fields | NOT_IMPLEMENTED |
| Central LLM client (retry/backoff/metrics) | NOT_IMPLEMENTED |
| LearningRepository + SQLite | NOT_IMPLEMENTED |
| pyproject/dev deps + CI (no live) | NOT_IMPLEMENTED |
| Test reorg + markers | NOT_IMPLEMENTED |
| Phase 3 DOCX/PDF/UI | OUT OF SCOPE — correctly absent |

---

## M. Files expected to change (by wave)

### Wave 1 (P0 correctness)
- `resume_engine/config/thresholds.py` (maybe add learning constants later; keep P4_USAGE_MAX SoT)
- `resume_engine/config/settings.py` (run dirs, rejected)
- `resume_engine/validation/coverage_validator.py`
- `resume_engine/repair/repair_planner.py`
- `resume_engine/repair/targeted_rewriter.py` (+ new patch apply helper)
- `resume_engine/repair/repair_validator.py`
- `resume_engine/reports/behavioral_audit.py`
- `resume_engine/pipeline/phase2_pipeline.py`
- `resume_engine/generation/resume_generator.py`
- `resume_engine/main.py` (`--run-id`)
- `resume_engine/models/resume_schema.py` / validation models (stable IDs / patch schema as needed)
- New tests under `tests/`

### Wave 2 (P1 quality)
- `variant_planner.py`, responsibility/laya/technology validators, provenance, cert models, Phase 1 test layer, audits, diversity regen

### Wave 3 (learning)
- `outcome_store.py`, `strategy_memory.py`, `strategy_builder.py` / planner hooks, eligibility config

### Wave 4 (infra)
- `.gitignore`, path helpers, `llm/client.py`, SQLite repo, `pyproject.toml` / CI, test layout

---

## N. Files that should NOT need modification

- Phase 3 DOCX/PDF/UI (do not create)
- Existing fixture JD texts (keep; extend tests around them)
- Committed sample storage artifacts (do not delete without explicit instruction)
- Core Phase 1 extraction prompts wholesale rewrite (extend certs carefully; do not redesign engine)
- Working validators’ hard-gate semantics for P1/P2/firewall unless fixing listed defects

---

## Classification summary (high-signal)

| Area | State |
|------|-------|
| Phase 1 blueprint engine | IMPLEMENTED (runtime exists); live correctness NOT_PROVEN in tests |
| Strategy builder | IMPLEMENTED |
| Fixed variant planner | PARTIALLY_IMPLEMENTED |
| OpenAI generation + skill provenance | IMPLEMENTED |
| Technology firewall | PARTIALLY_IMPLEMENTED |
| Coverage P1/P2 | IMPLEMENTED; P4 placement semantics BROKEN |
| P4 usage enforcement | NOT_IMPLEMENTED (+ audit BROKEN) |
| Repair planner/rewriter | PARTIALLY_IMPLEMENTED / BROKEN vs “targeted” claim |
| Failed-final gate | BROKEN |
| Artifact versioning / run_id | NOT_IMPLEMENTED |
| Learning feedback loop | NOT_IMPLEMENTED (storage PARTIAL) |
| Behavioral fixture tests | IMPLEMENTED |
| Implementation audit honesty | BROKEN |
| Privacy gitignore | BROKEN |

---

## STOP AND VERIFY

Wave 0 complete. **Do not start Wave 1 until this audit is accepted.**

Next wave order (mandatory):

1. Wave 1 — P4 + failed-final + immutable artifacts + run_id + patch repair + tests → full suite green  
2. Wave 2 — dynamic variants, certs, provenance, responsibility map, Laya batch, regen, audits  
3. Wave 3 — self-learning retrieval/eligibility  
4. Wave 4 — LLM client, SQLite, privacy, CI, path portability  

After each wave: report FILES MODIFIED/CREATED/DELETED, TESTS BEFORE/AFTER, NEW/FAILED/SKIPPED, audits, unresolved issues.
