# PHASE 2.7 GATE 4 — BASELINE (pre-change)

**Timestamp (UTC):** 2026-09-22T23:47:13Z  
**Branch:** `main`  
**Commit SHA:** `77543de0fc1661b9fe08b9efa69f55db09fcc22b`  
**Working tree:** clean  
**Python:** 3.12.6  
**OPENAI_API_KEY:** unset  

## Scope

1. Real opt-in live Phase 1 harness (no automatic paid spend)
2. Deeper DOCX branding polish
3. UI authentication (password gate when configured)
4. Drop JSONL read fallback (SQLite-only default reads; explicit path still JSONL for tests)

## Baseline metrics

| Metric | Value |
|--------|-------|
| `pytest -m "not live"` | **547** passed; **3** skipped; **0** failed |
| Live | LIVE_TEST_NOT_RUN (key unset) |
