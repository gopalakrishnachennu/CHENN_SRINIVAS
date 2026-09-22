# PHASE 2.7 GATE 3 — BASELINE (pre-change)

**Timestamp (UTC):** 2026-09-22T23:38:20Z  
**Branch:** `main`  
**Commit SHA:** `3ef34b90d95395e4f7b7c37578651facb7659cc6`  
**Working tree:** clean  
**Python:** 3.12.6  
**OPENAI_API_KEY:** unset  

## Scope

1. Historical Ruff (5 errors) → zero  
2. Coverage threshold enforcement (`fail_under=70`)  
3. SQLite sole learning write path (`dual_write_jsonl=False` by default)  
4. DOCX/PDF/UI stabilization polish (contact fields, both-export, PDF density)  
5. Live E2E: remain `LIVE_TEST_NOT_RUN` (no paid API spend)

## Baseline metrics

| Metric | Value |
|--------|-------|
| `pytest -m "not live"` | **541** passed; **3** skipped; **0** failed |
| Ruff | **5** errors |
| Coverage | **73.72%** → `coverage_gate3_baseline.json` |
| Live | LIVE_TEST_NOT_RUN |
