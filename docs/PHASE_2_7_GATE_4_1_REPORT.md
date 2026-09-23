# PHASE 2.7 GATE 4.1 REPORT — CI Reconciliation + Live Isolation + UI Hardening

**Status at write time:** pending GitHub Actions confirmation  
**Report written (UTC):** 2026-09-23T00:35:00Z  
**Starting commit:** `c550c45d1331720448d685a85ecf8da975acd15f`  
**Ending commit:** pending at write time  
**Branch:** `main`

Baseline: [`docs/PHASE_2_7_GATE_4_1_BASELINE.md`](PHASE_2_7_GATE_4_1_BASELINE.md)

---

## Summary

Gate 4 (`c550c45`) claimed local Ruff = 0 / PASS while GitHub CI failed on Ruff 0.16.8. Gate 4.1 pins Ruff to CI, clears all findings, isolates the live harness from production registry/blueprint storage, hardens login redirects and resume path containment, and corrects Gate 4 documentation.

---

## Dependency versions

| Tool | Version |
|------|---------|
| Python (local) | 3.12.6 |
| Ruff pin | `ruff==0.16.8` (`requirements-dev.txt` + `pyproject.toml`) |
| Local Ruff after pin | **0.16.8** |
| Baseline Ruff errors (0.16.8) | **91** |
| Final Ruff errors | **0** |

---

## Local verification

| Metric | Result |
|--------|--------|
| `pytest -m "not live"` | **569** passed / **3** skipped / **1** deselected |
| `pytest -q` | **569** passed / **4** skipped |
| Coverage | **75.03%** (`fail_under=70`) |
| `ruff check resume_engine tests` | **All checks passed!** |
| Live OpenAI | **LIVE_TEST_NOT_RUN** |
| Live Laya | **LIVE_TEST_NOT_RUN** |

---

## Implementations

### 1. Pin Ruff to CI
- `requirements-dev.txt` / `pyproject.toml`: `ruff==0.16.8`
- Safe `--fix` + manual equivalent edits for remaining SIM/BLE/S110/RUF rules

### 2. Live harness isolation
- Live writes only under `resume_engine/storage/reports/live/<run_id>/` (`registry.json`, `blueprint.json`, `evidence.json`)
- `load_registry` / `save_registry` / `update_registry_from_jd` / `save_blueprint` accept optional path injection (default Phase 1 behavior unchanged)
- Default registry hash checked before/after; harness fails if mutated
- Status semantics: OpenAI/Laya/full E2E fields; Laya skip ≠ full E2E PASS

### 3. UI redirect hardening
- `safe_next_url()` — only local `/...` paths; rejects `https://`, `//`, `javascript:`

### 4. UI path containment
- `resolve_validated_resume_path()` — `Path.resolve()` + `relative_to(RUNS_STORAGE_DIR)` + exists/file/`validated/` checks
- Used by `/view` and `/export`

### 5. Documentation correction
- Gate 4 report appends post-commit CI reconciliation note
- This Gate 4.1 report is the release status of record

---

## Files

### Created
- `docs/PHASE_2_7_GATE_4_1_BASELINE.md`
- `docs/PHASE_2_7_GATE_4_1_REPORT.md`
- `resume_engine/ui/paths.py`
- `tests/test_phase27_gate4_1.py`
- `coverage_gate4_1_final.json`

### Modified
| File | Why |
|------|-----|
| `requirements-dev.txt` / `pyproject.toml` | Pin Ruff 0.16.8 |
| `resume_engine/live/phase1_harness.py` | Isolated live storage + status semantics |
| `jd_blueprint_engine.py` | Optional registry/blueprint path injection |
| `resume_engine/ui/auth.py` | `safe_next_url` |
| `resume_engine/ui/app.py` | Use safe redirect + path helper |
| `docs/PHASE_2_7_GATE_4_REPORT.md` | CI reconciliation correction |
| Many lint-touched modules under `resume_engine/` / `tests/` | Ruff 0.16.8 clean |

---

## Proof table

| Criterion | Result |
|-----------|--------|
| Ruff locally | **PASS** (0) |
| Ruff GitHub Python 3.11 | pending |
| Ruff GitHub Python 3.12 | pending |
| Offline tests | **PASS** (569/3) |
| Coverage ≥70 | **PASS** (75.03%) |
| Live harness isolated | **PASS** |
| Default registry unchanged | **PASS** |
| External login redirect blocked | **PASS** |
| Path traversal blocked | **PASS** |
| Symlink escape blocked | **PASS** |
| Live OpenAI | **LIVE_TEST_NOT_RUN** |
| Live Laya | **LIVE_TEST_NOT_RUN** |

---

## Unresolved

1. Paid live OpenAI/Laya still opt-in only (not required for Gate 4.1 PASS).
2. GitHub Actions results filled after push.

---

# PHASE 2.7 GATE 4.1 STATUS: INCOMPLETE

Blocker at write time: GitHub Python 3.11 / 3.12 job results not yet confirmed.
