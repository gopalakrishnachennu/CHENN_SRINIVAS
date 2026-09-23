# PHASE 2.7 GATE 4 REPORT — Live Harness, DOCX Branding, UI Auth, SQLite Reads

**Status:** `PHASE 2.7 GATE 4 STATUS: PASS`  
**Report written (UTC):** 2026-09-22T23:53:00Z  
**Starting commit:** `77543de0fc1661b9fe08b9efa69f55db09fcc22b`  
**Ending state:** Gate 4 commit pending at write time  
**Branch:** `main`

Baseline: [`docs/PHASE_2_7_GATE_4_BASELINE.md`](PHASE_2_7_GATE_4_BASELINE.md)

---

## Metrics

| Metric | Baseline | Final |
|--------|----------|-------|
| `pytest -m "not live"` | 547 pass / 3 skip | **554** pass / **3** skip / **0** fail |
| `pytest -q` | — | **554** pass / **4** skip |
| Ruff | 0 errors | **0** errors |
| Coverage | 73.97% | **73.95%** (`fail_under=70` enforced) |
| Behavioral audit | PASS | **PASS** |
| Implementation audit | 42/42 | **44/44** (added `ui_auth`, `phase1_live_harness`) |
| Live OpenAI/Laya | LIVE_TEST_NOT_RUN | **LIVE_TEST_NOT_RUN** (`OPENAI_API_KEY` unset; no paid spend) |

---

## Implementations

### 1. Real opt-in live Phase 1 harness
- `resume_engine/live/phase1_harness.py`: preflight + `run_phase1_live_harness`
- Requires `RUN_LIVE_TESTS=1` **and** non-placeholder `OPENAI_API_KEY`
- Without both: `LIVE_TEST_NOT_RUN` (pytest skip); never contacts OpenAI
- Writes evidence under `resume_engine/storage/reports/live/` when executed
- `tests/test_phase1_offline.py` wired to harness; Gate 4 preflight unit tests prove skip paths

### 2. Deeper DOCX branding
- Accent teal `#0F5C4C` on title subtitle, section headings, skill labels
- Bottom borders under contact band and section headings
- Calibri ink/muted hierarchy retained; no layout redesign

### 3. UI authentication
- `resume_engine/ui/auth.py`: optional password gate via `RESUME_ENGINE_UI_PASSWORD`
- Username defaults to `operator` (`RESUME_ENGINE_UI_USER`); optional `RESUME_ENGINE_UI_SECRET`
- When password unset: auth disabled (banner); local open use preserved
- Routes: `/login`, `/logout`, `/healthz` (public); remaining routes `@require_auth`

### 4. Drop JSONL read fallback
- `load_outcome_records()` default path is **SQLite-only**
- Explicit `path=` still reads JSONL for tests/tooling
- Gate 2 preference test updated for Gate 4 semantics

---

## Files

### Created
- `docs/PHASE_2_7_GATE_4_BASELINE.md`
- `docs/PHASE_2_7_GATE_4_REPORT.md`
- `resume_engine/live/__init__.py`
- `resume_engine/live/phase1_harness.py`
- `resume_engine/ui/auth.py`
- `tests/test_phase27_gate4.py`
- `coverage_gate4_final.json`

### Modified
| File | Why |
|------|-----|
| `resume_engine/export/docx_exporter.py` | Accent + borders branding |
| `resume_engine/learning/strategy_memory.py` | SQLite-only default reads |
| `resume_engine/ui/app.py` | Login/logout/healthz + auth gate |
| `resume_engine/reports/implementation_audit.py` | Register auth + live harness |
| `tests/test_phase1_offline.py` | Live test calls harness |
| `tests/test_phase27_gate2.py` | SQLite-only read assertion |
| `tests/test_wave3_learning.py` | Ruff unused import |
| `.env.example` | UI auth + live opt-in vars |

### Deleted
None.

---

## Proof table

| Criterion | Result |
|-----------|--------|
| Live harness exists + preflight skips without flag/key | PASS |
| Live E2E not auto-run without credentials | LIVE_TEST_NOT_RUN |
| DOCX headings use accent color | PASS |
| UI redirects when password configured | PASS |
| UI open when password unset | PASS |
| Default `load_outcome_records` ignores orphan JSONL | PASS |
| Explicit JSONL path still works | PASS |
| Ruff clean | PASS |
| Coverage ≥ 70% | PASS (73.95%) |
| Behavioral audit | PASS |
| Full offline pytest | PASS (554/3) |

---

## DISCOVERED_NOT_FIXED_GATE4

1. Paid live OpenAI/Laya run still requires operator credentials (`RUN_LIVE_TESTS=1` + real key) — intentionally not executed this gate.
2. Full ATS redesign / alternate branded DOCX templates — out of scope.
3. Multi-user accounts / OAuth / CSRF hardening beyond session password — out of scope.
4. Coverage ratchet above 70 toward 80%+ — future only.
5. Physical move of all tests into `unit/integration/behavioral/live` packages — still deferred.

---

# PHASE 2.7 GATE 4 STATUS: PASS

Phase 2.7 freeze gates 1–4 complete for deferred critical/hygiene/export/live-auth scope.

---

## Post-commit CI reconciliation (Gate 4.1)

GitHub Actions on `c550c45` **failed** under Ruff **0.16.8** (~91 findings on both Python 3.11 and 3.12).  
Local Gate 4 verification used Ruff **0.8.4**, which reported 0 errors — a tooling mismatch, not a green CI proof.

**Gate 4 final release status is superseded by Gate 4.1.**  
See [`docs/PHASE_2_7_GATE_4_1_REPORT.md`](PHASE_2_7_GATE_4_1_REPORT.md).
