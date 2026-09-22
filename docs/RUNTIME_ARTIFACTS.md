# Runtime artifacts — source-control policy (Phase 2.6 Wave 4)

## What is ignored going forward

`.gitignore` now excludes production runtime outputs:

- `resume_engine/storage/runs/`
- `resume_engine/storage/generated/`
- `resume_engine/storage/validated/`
- `resume_engine/storage/rejected/`
- `resume_engine/storage/learning/`
- `resume_engine/storage/reports/`
- `resume_engine/storage/strategies/`
- `resume_engine/storage/db/`
- `*.sqlite3` / `*.sqlite`

Environment secrets (`.env`, `.env.local`) remain ignored.

## What we did NOT do automatically

Existing committed sample artifacts under `resume_engine/storage/` were **not** deleted
or bulk-untracked. Some may be sanitized development fixtures used for local inspection.

Destroying or rewriting git history for those files requires an explicit human decision.

## How to safely untrack runtime artifacts later

After confirming which paths are samples vs real customer data:

```bash
# Example — stop tracking without deleting local files
git rm -r --cached resume_engine/storage/runs
git rm -r --cached resume_engine/storage/generated
git rm -r --cached resume_engine/storage/validated
git rm -r --cached resume_engine/storage/rejected
git rm -r --cached resume_engine/storage/learning
git rm -r --cached resume_engine/storage/reports
git rm -r --cached resume_engine/storage/db

git add .gitignore docs/RUNTIME_ARTIFACTS.md
git commit -m "Stop tracking runtime resume engine storage artifacts"
```

Review `git status` carefully before committing. Do not force-push unless explicitly required.

## SQLite location

Default Wave 4 database path:

`resume_engine/storage/db/resume_engine.sqlite3`

JSONL learning files remain dual-written for backward compatibility under
`resume_engine/storage/learning/` (also ignored for new commits).
