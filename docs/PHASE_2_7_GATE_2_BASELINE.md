# PHASE 2.7 GATE 2 — BASELINE (pre-change)

**Timestamp (UTC):** 2026-09-22T23:02:01Z  
**Branch:** `main`  
**Commit SHA:** `ada661142b76c72f463963b94eeb475cd84e6513`  
**Working tree:** clean  
**Python:** 3.12.6  

## Scope (inferred from Gate 1 deferred semantic/learning items)

No separate Gate 2 mission brief existed in-repo. Gate 2 implements:

1. Cross-run fingerprint redesign (SimHash + preview↔preview; keep SHA256)
2. Responsibility semantic hardening + uncovered-ID feed to Laya
3. Laya responsibilities budget (remove hard `[:8]` truncation)
4. SQLite as learning read SoT (JSONL fallback; dual-write retained)
5. Validated final pointer sync after regeneration

Out of Gate 2 (deferred further): full Ruff mass-fix, coverage threshold enforcement, DOCX/PDF/UI polish, auth, ATS/job portals, Phase 1 live E2E.

## Baseline metrics

| Metric | Value |
|--------|-------|
| `pytest -m "not live"` | **528** passed; **3** skipped; **1** deselected; **0** failed |
| Ruff | **7** errors (historical) |
| Coverage | **73.04%** → `coverage_gate2_baseline.json` |
| Live tests | LIVE_TEST_NOT_RUN |
