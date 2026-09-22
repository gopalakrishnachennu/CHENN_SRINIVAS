# PHASE 2.7 GATE 3 REPORT — Hygiene + Export Stabilization

**Status:** `PHASE 2.7 GATE 3 STATUS: PASS`  
**Report written (UTC):** 2026-09-22T23:45:00Z  
**Starting commit:** `3ef34b90d95395e4f7b7c37578651facb7659cc6`  
**Ending state:** Gate 3 commit pending at write time  
**Branch:** `main`

Baseline: [`docs/PHASE_2_7_GATE_3_BASELINE.md`](PHASE_2_7_GATE_3_BASELINE.md)

---

## Metrics

| Metric | Baseline | Final |
|--------|----------|-------|
| `pytest -m "not live"` | 541 pass / 3 skip | **547** pass / **3** skip / **0** fail |
| `pytest -q` | — | **547** pass / **4** skip |
| Ruff | **5** errors | **0** errors |
| Coverage | 73.72% | **73.97%** (`fail_under=70` enforced) |
| Behavioral audit | PASS | **PASS** |
| Live OpenAI/Laya | LIVE_TEST_NOT_RUN | **LIVE_TEST_NOT_RUN** (`OPENAI_API_KEY` unset; no paid spend) |

---

## Implementations

### 1. Historical Ruff → clean
Fixed all 5 historical issues:
- `resume_engine/ui/app.py` unused `url_for` import (Jinja still provides it)
- `tests/test_behavioral_fixtures.py` unused `plan` assign
- `tests/test_wave2_p1.py` unused `SimpleNamespace` / `pytest`
- `tests/test_wave3_learning.py` unused `pytest`

CI Ruff is now **blocking** (removed `continue-on-error`).

### 2. Coverage threshold
- `pyproject.toml` `[tool.coverage.report] fail_under = 70`
- CI runs `pytest -m "not live" --cov=resume_engine --cov-fail-under=70`
- Actual coverage **73.97%** ≥ 70

### 3. SQLite sole write SoT
- `LearningRepository(dual_write_jsonl=False)` default
- `get_default_repository()` defaults SQLite-only
- Opt-in legacy JSONL: `LEARNING_DUAL_WRITE_JSONL=1` or explicit `dual_write_jsonl=True`
- `append_outcome_jsonl_only()` remains for intentional backup export
- Wave4 dual-write test still proves opt-in path

### 4. DOCX/PDF/UI polish (stabilization, not redesign)
- UI contact form: phone, location, linkedin, website (+ existing name/email)
- **Export both** returns a **ZIP** with DOCX+PDF (no silent single-file download)
- PDF: slightly denser margins/typography for less sparse pages
- No auth, no ATS, no branding redesign

### 5. Live E2E
- Not executed: `OPENAI_API_KEY` unset
- Existing `@pytest.mark.live` stub remains opt-in
- Report: **LIVE_TEST_NOT_RUN**

---

## Files

### Created
- `docs/PHASE_2_7_GATE_3_BASELINE.md`
- `docs/PHASE_2_7_GATE_3_REPORT.md`
- `tests/test_phase27_gate3.py`
- `coverage_gate3_baseline.json` / `coverage_gate3_final.json`

### Modified
| File | Why |
|------|-----|
| `resume_engine/ui/app.py` | Contact fields + ZIP both-export; Ruff |
| `resume_engine/export/pdf_exporter.py` | Denser layout |
| `resume_engine/learning/repository.py` | SQLite-only default + env opt-in |
| `tests/test_behavioral_fixtures.py` | Ruff |
| `tests/test_wave2_p1.py` | Ruff |
| `tests/test_wave3_learning.py` | Ruff |
| `pyproject.toml` | Coverage fail_under |
| `.github/workflows/tests.yml` | Cov floor + blocking Ruff |

### Deleted
None.

---

## Proof table

| Criterion | Result |
|-----------|--------|
| Ruff clean (`ruff check resume_engine tests`) | PASS (0 errors) |
| Coverage ≥ 70% enforced | PASS (73.97%) |
| Default learning write is SQLite-only | PASS |
| Opt-in JSONL dual-write still works | PASS |
| UI exposes extended contact fields | PASS |
| Export both returns ZIP with DOCX+PDF | PASS |
| PDF export still produces non-trivial file | PASS |
| Behavioral audit | PASS |
| Full offline pytest | PASS (547/3) |
| Live E2E | LIVE_TEST_NOT_RUN |

---

## DISCOVERED_NOT_FIXED_GATE3

1. Real live Phase 1 OpenAI/Laya E2E harness still a stub — needs credentials + dedicated Gate 4/live mission.
2. Full DOCX visual redesign / branded templates — out of scope.
3. UI authentication — out of scope.
4. Dropping JSONL **read** fallback entirely — kept for migration safety.
5. Coverage raise above 70 toward 80%+ — future ratchet only.

---

# PHASE 2.7 GATE 3 STATUS: PASS

Gate 4 (live E2E / deeper export branding) not started.
