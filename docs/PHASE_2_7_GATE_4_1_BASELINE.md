# PHASE 2.7 GATE 4.1 — BASELINE (pre-change)

**Timestamp (UTC):** 2026-09-23T00:20:00Z  
**Branch:** `main`  
**Commit SHA:** `c550c45d1331720448d685a85ecf8da975acd15f`  
**Working tree:** dirty — only `resume_engine/storage/reports/IMPLEMENTATION_AUDIT.{json,txt}` (runtime regenerations; not Gate 4.1 scope)  
**Python:** 3.12.6  
**pip:** 24.2  
**OPENAI_API_KEY:** not used for baseline  

## Scope

CI reconciliation: pin Ruff to CI version, clean all Ruff findings, isolate live harness storage, harden UI redirect + path containment, correct Gate 4 documentation, make GitHub Actions green on 3.11 + 3.12.

## Baseline metrics (do not trust older Gate 4 markdown)

| Metric | Value |
|--------|-------|
| Local Ruff binary | **0.8.4** (via `python3 -m ruff`) |
| `requirements-dev.txt` Ruff pin | `ruff>=0.6` (floating — mismatch with CI) |
| Local `ruff check resume_engine tests` (0.8.4) | **0 errors** (All checks passed) |
| Local `ruff check` after installing **0.16.8** (pre-fix) | **91 errors** |
| GitHub CI Ruff (reported on `c550c45`) | **0.16.8** with **~91 errors** (both 3.11 and 3.12 red) |
| `pytest -m "not live"` | **554** passed; **3** skipped; **1** deselected; **0** failed |
| Coverage (last Gate 4 final JSON) | **73.95%** (`fail_under=70`) |
| Live OpenAI/Laya | **LIVE_TEST_NOT_RUN** |

## Known discrepancies vs Gate 4 report

Gate 4 report claimed Ruff = 0 and overall PASS; GitHub Actions on `c550c45` failed Ruff under 0.16.8. Gate 4.1 supersedes release status.
