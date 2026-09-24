# PHASE 3.2.1 — PRODUCTION DATA STABILIZATION REPORT

Regression discovered after Phase 3.2 `FINAL WORKFLOW STABILIZATION STATUS: PASS`.

Root cause: the Phase 3.2 test suite wrote candidates/jobs into the **production** SQLite file because:

1. `tests/ui/_helpers.py` did not isolate the DB.
2. `resume_engine/ui/app.py` called `create_app()` at **import time**, opening production SQLite before pytest fixtures could redirect the path.
3. Matching treated Family Registry `compatible` as normal recommendations, so removing secondary family did not clear DE jobs for an AI/ML candidate.
4. Matches loaded up to 2000 jobs, N+1 family SQL lookups, no pagination, and offered Create Resume for non-READY jobs.

## Commits

| | SHA |
|---|---|
| Starting commit | `3a965b9b16ae99e7d79b8257c5f48627a228a852` |
| Ending commit | `PENDING_FINALIZE` |

## Fixes delivered

### Absolute test DB isolation

- Runtime `get_sqlite_db_path()` honors `RESUME_ENGINE_DB_PATH`.
- Production path remains `resume_engine/storage/db/resume_engine.sqlite3`.
- `tests/conftest.py` autouse fixture redirects DB + UI storage to `tmp_path`.
- Hard raise: `TEST_DATABASE_ISOLATION_VIOLATION` if pytest resolves the production DB.
- Removed import-time `app = create_app()` (lazy via `main()` only).
- CI asserts test path ≠ production and SHA256 of production DB unchanged across the suite.

### Data audit + safe cleanup

```bash
python3 -m resume_engine.maintenance.data_audit --check
python3 -m resume_engine.maintenance.data_audit --backup
python3 -m resume_engine.maintenance.data_audit --clean-test-contamination --dry-run
python3 -m resume_engine.maintenance.data_audit --clean-test-contamination
```

Cleanup removed **77** test candidates and **77** test jobs (including `Pending AI Role` / `Pending Only Role` / `UI Cand *` / `E2E Cand` / `test_blueprints` paths).

### Post-cleanup production snapshot

| Metric | Value |
|---|---|
| Candidates | 8 |
| Active jobs | 21 |
| READY | 0 |
| NEEDS_ANALYSIS | 21 |
| Known test-string contamination | **0** |

### Strict matching (default)

- DIRECT / SECONDARY / HYBRID exact-overlap only.
- COMPATIBLE only via Advanced “Include adjacent families” (off by default).
- Removing secondary immediately drops secondary-only matches (HTTP-proven).

### READY-only resume matches

- Matches / Create / Dashboard counts use READY + valid blueprint + strict match.
- NEEDS_ANALYSIS stays on Jobs.

### Dedup + idempotent import

- Content hash / job URL reuse in `analyze_and_store` and workbook import.

### Performance / UX

- Family registry loaded once per match request (`FamilyRegistrySnapshot`).
- `list_jobs_lite` for matching (no heavy blueprint revalidation).
- Matches paginated (20/page), compact rows, explainable counts.

## Verification

| Check | Result |
|---|---|
| Targeted isolation/strict/e2e/ui tests | PASS |
| Full `pytest -m "not live"` | **710 passed**, cov **70.77%** |
| Ruff | PASS |
| Production SQLite SHA256 unchanged across full suite | PASS |
| `data_audit --check` contamination | **0** |
| CI Python 3.11 / 3.12 | PENDING push |

## Proof table

| Criterion | Status |
|---|---|
| Tests cannot touch production DB | PASS |
| Production DB hash unchanged after full tests | PASS |
| Test blueprints isolated | PASS |
| Contaminated data audit exists | PASS |
| Safe cleanup exists | PASS |
| Strict matching default | PASS |
| Secondary removal drops secondary-only matches | PASS |
| COMPATIBLE not in normal recommendations | PASS |
| Only READY jobs count as matches | PASS |
| Duplicate imports idempotent | PASS |
| Duplicate JDs blocked/reused | PASS |
| Matches paginated | PASS |
| No N+1 family-registry querying | PASS |
| Counts = unique DB records | PASS |
| Known test strings absent from production | PASS |
| Full tests | PASS |
| Ruff | PASS |
| CI 3.11 / 3.12 | PENDING |

---

**PHASE 3.2.1 PRODUCTION DATA STABILIZATION STATUS: INCOMPLETE**

Blocker: GitHub CI pending after push.
