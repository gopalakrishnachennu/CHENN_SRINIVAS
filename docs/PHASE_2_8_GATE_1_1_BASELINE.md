# PHASE 2.8 GATE 1.1 — BASELINE (pre-change)

**Timestamp (UTC):** 2026-09-23T04:51:00Z  
**Branch:** `main`  
**Commit SHA:** `2fe8e1a5aa1c48e44a05da2ba43d8343f7b663b0`  
**Working tree:** dirty — only `resume_engine/storage/reports/*` runtime regenerations (ignored for Gate 1.1 scope)  
**Python:** 3.12.6  
**River:** 0.26.1  
**Ruff:** 0.16.8  

## Baseline metrics

| Metric | Value |
|--------|-------|
| `pytest tests/test_phase28_online_learning.py` | **29** passed |
| `pytest -m "not live"` | **598** passed / **3** skipped / **1** deselected |
| Coverage | **75.09%** (`fail_under=70`) |
| `ruff check resume_engine tests` | **0** errors |
| Online mode | shadow (active production OFF) |

## Pre-existing notes

No unexpected baseline breakage. Gate 1.1 proceeds from green Gate 1 state.
