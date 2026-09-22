# PHASE 2.7 GATE 2 REPORT — Semantic Correctness + Learning SoT

**Status:** `PHASE 2.7 GATE 2 STATUS: PASS`  
**Report written (UTC):** 2026-09-22T23:07:49Z  
**Starting commit:** `ada661142b76c72f463963b94eeb475cd84e6513` (Gate 1)  
**Ending state:** working tree dirty with Gate 2 edits (commit pending)  
**Branch:** `main`

Baseline: [`docs/PHASE_2_7_GATE_2_BASELINE.md`](PHASE_2_7_GATE_2_BASELINE.md)

> No separate Gate 2 mission brief existed in-repo. Scope was taken from Gate 1 deferred semantic/learning items (not Ruff mass-fix, not DOCX/PDF/UI, not live E2E).

---

## Metrics

| Metric | Baseline | Final |
|--------|----------|-------|
| `pytest -m "not live"` | 528 pass / 3 skip | **541** pass / **3** skip / **0** fail |
| `pytest -q` | — | **541** pass / **4** skip |
| Ruff | 7 | **5** (historical; Gate 2 introduced none) |
| Coverage | 73.04% | **73.72%** |
| Behavioral audit | PASS | **PASS** |
| Live OpenAI/Laya | LIVE_TEST_NOT_RUN | **LIVE_TEST_NOT_RUN** |

Gate 2 tests: `tests/test_phase27_gate2.py` — all passed. Gate 1 suite still passes.

---

## Fixes implemented

### 1. Cross-run fingerprint redesign
- Added `resume_engine/learning/fingerprint_signatures.py` (SimHash-64 + MinHash, no external deps).
- Fingerprints now store `simhash64`, `minhash`, `signature_version=2` plus SHA256 + preview.
- Comparison order: exact SHA256 → signature near-duplicate → **preview↔preview** SequenceMatcher (no longer full-text vs truncated preview).
- Thresholds: `FINGERPRINT_SIMHASH_MAX_HAMMING=6`, `FINGERPRINT_MINHASH_JACCARD_MIN=0.85`.

### 2. Responsibility semantics
- Keyword overlap + **bigram phrase boost** + technology evidence.
- Exposes `uncovered_responsibility_ids` for Laya prioritization.
- Pipeline passes uncovered IDs into `validate_with_laya`.

### 3. Laya responsibilities budget
- Removed hard `responsibilities[:8]`.
- New `LAYA_RESPONSIBILITY_MAX=24` with structured entries, truncation diagnostics.
- Prefers uncovered R IDs first when budget binds.
- Phase 1 `make_compact_laya_state` aligned to same budget.

### 4. SQLite learning read SoT
- `load_outcome_records()` prefers `LearningRepository.get_strategy_history(...)`.
- Explicit `path=` still reads JSONL (wave tests unchanged).
- Dual-write retained for backup; JSONL fallback if SQLite empty.

### 5. Validated final pointer sync
- Regeneration **syncs** `V{id}_final.json` to selected attempt content.
- Attempt files remain immutable; marker `*_final_selected_attempt.json` always written.
- Added `resolve_validated_final()`.
- UI lists stable finals only (excludes `*_attempt_*_final.json`).

---

## Files

### Created
- `docs/PHASE_2_7_GATE_2_BASELINE.md`
- `docs/PHASE_2_7_GATE_2_REPORT.md`
- `resume_engine/learning/fingerprint_signatures.py`
- `tests/test_phase27_gate2.py`
- `coverage_gate2_baseline.json` / `coverage_gate2_final.json`

### Modified
| File | Why |
|------|-----|
| `resume_engine/config/thresholds.py` | Laya budget + fingerprint thresholds |
| `resume_engine/learning/fingerprint_store.py` | Signature-aware uniqueness |
| `resume_engine/learning/strategy_memory.py` | SQLite read SoT |
| `resume_engine/learning/repository.py` | Unused-import cleanup |
| `resume_engine/validation/laya_validator.py` | Responsibility budget + uncovered prefer |
| `resume_engine/validation/responsibility_validator.py` | Bigram boost + uncovered IDs |
| `resume_engine/pipeline/phase2_pipeline.py` | Wire uncovered IDs to Laya |
| `resume_engine/storage/run_store.py` | Stable final sync + resolver |
| `resume_engine/ui/app.py` | Stable-final listing |
| `jd_blueprint_engine.py` | Phase 1 Laya state budget align |
| `tests/test_phase27_gate1.py` | Final pointer sync expectation |

### Deleted
None.

---

## Proof table

| Criterion | Result |
|-----------|--------|
| SimHash/MinHash signatures stored | PASS |
| Near-duplicate paraphrase flagged cross-run | PASS |
| Different content not flagged | PASS |
| Laya responsibilities not hard-capped at 8 | PASS |
| Uncovered R IDs preferred in Laya budget | PASS |
| Responsibility uncovered IDs exposed | PASS |
| SQLite preferred for default outcome load | PASS |
| Explicit JSONL path still works | PASS |
| Stable `V01_final.json` syncs after regen | PASS |
| Attempt history preserved | PASS |
| Gate 1 tests still pass | PASS |
| Behavioral audit | PASS |
| Full offline pytest | PASS (541/3) |

---

## DISCOVERED_NOT_FIXED_GATE2

1. Historical Ruff unused imports (ui template `url_for`, wave2/wave3, behavioral fixture) — Gate 3.
2. Coverage threshold enforcement — Gate 3/4.
3. Full embedding-based responsibility semantics (beyond bigram/tech boost) — future.
4. Dropping JSONL dual-write entirely — future (kept as backup).
5. DOCX/PDF/UI polish, auth, ATS/job portals — out of stabilization scope.
6. Phase 1 live E2E — LIVE_TEST_NOT_RUN.
7. Historical fingerprints without signatures still rely on preview↔preview only.

---

# PHASE 2.7 GATE 2 STATUS: PASS

Do not begin Gate 3 from this report alone. Production readiness requires Gates 1–4 independently verified.
