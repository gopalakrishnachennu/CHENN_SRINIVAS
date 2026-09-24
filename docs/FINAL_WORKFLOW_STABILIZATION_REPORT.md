# FINAL WORKFLOW STABILIZATION REPORT

Phase 3.2 — End-to-End Data & Workflow Stabilization

## Commits

| | SHA |
|---|---|
| Starting commit | `ce808c0d31d51f2451accea7514e92ced3364101` |
| Ending commit | _(filled after finalize commit)_ |

## Root causes found

1. **Trusted stored `blueprint_path`** — Create Resume / preflight treated DB path as truth; missing/deleted files surfaced as raw `Job has no blueprint_path` errors.
2. **Persisted matches treated as permanent** — Candidate secondary family cleared to `""` / left stale; Matches / Create still showed secondary-only jobs.
3. **Generate allowed before READY** — UI did not gate on `analysis_status == READY` + valid blueprint + live family match.
4. **Imported jobs could look resume-ready** — Import must land as `NEEDS_ANALYSIS` without blueprint.

## Fixes

### Blueprint lifecycle

- New `resume_engine/ui/services/blueprint_lifecycle.py` with `ensure_job_blueprint(job_id)`.
- Behavior: analyze → create → persist; regenerate on missing/stale/deleted; reuse when valid.
- Create Resume always calls `ensure_job_blueprint` before Phase 2; never trusts bare path.
- On analysis failure: `analysis_status = FAILED` (never READY without file).

### Match invalidation

- Single authoritative `match_candidate_to_job` / `list_matches_for_candidate`.
- Rules: DIRECT → SECONDARY → HYBRID (set overlap) → COMPATIBLE (registry) → NO_MATCH.
- `invalidate_matches_for_candidate` / `_for_job` / `_all`; version-stamped optional cache.
- Family registry updates invalidate all matches.

### Candidate update

- `secondary_family_id = None` (never `""` / `"None"` / `"null"`).
- `primary == secondary` normalized to secondary `None`.
- Atomic: validate → save → bump `version` → invalidate/recompute → return fresh profile.
- Archive invalidates matches.

### JD update

- Raw JD text change: clear blueprint, `NEEDS_ANALYSIS`, invalidate matches, require re-analysis.
- Family field changes invalidate job matches.
- Archive invalidates matches.

### Import

- Excel/CSV import inserts `analysis_status = NEEDS_ANALYSIS` (no auto-READY).
- Jobs UI: status badges + **Analyze Pending Jobs**.
- Create page: Analyze Now / Retry Analysis via `ensure_job_blueprint`.

### Preflight

- `preflight_create_resume` structured codes: `JOB_BLUEPRINT_NOT_READY`, `FAMILY_NO_LONGER_MATCHES`, `CANDIDATE_COMPANY_HISTORY_MISSING`, `JOB_ARCHIVED`, etc.
- Fail before OpenAI / Phase 2.
- River remains SHADOW.

### UI

- Create: Candidate → Matching Jobs → Generate; badges READY / NEEDS ANALYSIS / FAILED / ARCHIVED.
- Only READY + matched jobs selectable; Generate disabled until READY selected.
- No raw `blueprint_path` error strings.
- Matches: live query via `candidate_id` / `candidate`; Advanced → System integrity panel (red if failures > 0).

### Reconciliation

```bash
python3 -m resume_engine.maintenance.reconcile --check
python3 -m resume_engine.maintenance.reconcile --repair
```

Detects READY-without-blueprint, stale hashes, orphan paths, unknown families, secondary sentinels, stale match cache.

## Tests

| Suite | Result |
|---|---|
| Targeted (`test_end_to_end_integrity` + `tests/ui`) | PASS |
| Full `pytest -m "not live"` | **694 passed**, 3 skipped, 1 deselected |
| Coverage | **72.54%** (≥70) |
| Ruff | **All checks passed** |

## Reconciliation result

```json
{
  "jobs_total": 98,
  "jobs_ready": 50,
  "jobs_needs_analysis": 39,
  "jobs_failed": 0,
  "candidates": 85,
  "candidates_without_primary": 0,
  "stale_matches": 0,
  "issue_count": 0,
  "ok": true
}
```

## GitHub CI

| Matrix | Status |
|---|---|
| Python 3.11 | _(pending push)_ |
| Python 3.12 | _(pending push)_ |

## Proof table

| Item | Status |
|---|---|
| Missing blueprint handled | PASS |
| No raw blueprint_path error | PASS |
| Candidate family edit refreshes match | PASS |
| Secondary removal removes stale match | PASS |
| JD edit invalidates blueprint | PASS |
| JD edit recomputes matches | PASS |
| Unmatched JD cannot generate | PASS |
| Archived JD cannot generate | PASS |
| Imported JD analyzed correctly | PASS |
| Preflight works | PASS |
| Stale cache impossible/detected | PASS |
| Full tests | PASS |
| Ruff | PASS |
| CI Python 3.11 | PENDING |
| CI Python 3.12 | PENDING |

## Manual flows (engine-level)

| Flow | Result |
|---|---|
| A — AI+DE secondary sees AI + DE; Salesforce hidden | PASS (matcher + Create filter) |
| B — Remove secondary; DE disappears unless registry-compatible | PASS (regression clears compatible for NO_MATCH; default registry may keep COMPATIBLE) |
| C — Import without blueprint → prepare → READY | PASS |
| D — JD text change → stale → new blueprint | PASS |

---

**FINAL WORKFLOW STABILIZATION STATUS: INCOMPLETE**

Blockers: GitHub CI Python 3.11 / 3.12 not yet green on this commit; ending SHA pending finalize.
