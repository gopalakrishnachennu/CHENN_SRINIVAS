# PHASE 2.7 GATE 1 — BASELINE (pre-change)

**Timestamp (UTC):** 2026-09-22T15:05:26Z  
**Branch:** `main`  
**Commit SHA:** `4e27d5b43c5a4c56c1404c2eee3b78a063d2cacc`  
**Working tree:** clean (no modified/untracked files before Gate 1 edits)  
**Python:** 3.12.6  
**pip:** 24.2  

## Environment capture

```text
pwd=/Users/gopalakrishnachennu/Desktop/CHENN_SRINIVAS
git branch --show-current=main
git rev-parse HEAD=4e27d5b43c5a4c56c1404c2eee3b78a063d2cacc
python3 --version=Python 3.12.6
```

## Pre-existing modifications

None. Working tree matched `origin/main` at the audited commit.

## Baseline metrics (Step 2 — recorded before Gate 1 code edits)

| Metric | Value |
|--------|-------|
| `pytest -q` | collected **471**; **467** passed; **0** failed; **4** skipped |
| `pytest -m "not live"` | **467** passed; **3** skipped; **1** deselected |
| Behavioral audit | **PASS** |
| Implementation audit | Importable **42/42** (`tested=false` on import) |
| Ruff (`python3 -m ruff check resume_engine tests`) | **9** errors (historical; not Gate 1 scope) |
| Coverage (`not live`) | **73.14%** → `coverage_gate1_baseline.json` |

Live OpenAI/Laya: `LIVE_TEST_NOT_RUN`
