# Phase 3.1 — Resume Intelligence Control Center Architecture

## Purpose

Phase 3.1 adds a professional Flask/Jinja **operator control center** around the
existing Phase 1 / Phase 2 / Phase 2.8 resume engine. It does **not** replace
validators, scoring, River, exporters, or pipeline logic.

River production ranking remains **shadow-only**. Active mode is locked in UI
and configuration services.

## Layering

```text
Browser UI (Jinja + CSS + JS)
   ↓
Flask Routes / API          resume_engine/ui/routes/*, app.py
   ↓
UI Service Layer            resume_engine/ui/services/*
   ↓
Configuration Service       config_service.py (SAFE / ADVANCED / LOCKED)
   ↓
Existing Resume Engine      Phase 1, strategy, Phase 2, validators, repair, River, export
   ↓
SQLite / Filesystem         same SQLITE_DB_PATH + storage dirs
   ↓
OpenAI / Laya / River
```

## Package layout

```text
resume_engine/ui/
  app.py              factory, auth, health, job status API, blueprint registration
  auth.py             session auth + safe-next redirects
  csrf.py             CSRF token + @csrf_protect
  db.py               UI schema (create-if-not-exists) on shared SQLite
  paths.py            validated path containment
  app_helpers.py      shared UI helpers
  routes/             one blueprint per nav section
  services/           thin adapters over existing engine
  templates/          base + pages + components
  static/css|js       desktop-first enterprise styling
```

Launch:

```bash
export RESUME_ONLINE_LEARNING_MODE=shadow
python3 phase_3_export.py ui
```

## Navigation / routes

| Page | Prefix |
|------|--------|
| Dashboard | `/` |
| JD Workspace | `/jd/` |
| Blueprints | `/blueprints/` |
| Candidates | `/candidates/` |
| Strategies | `/strategies/` |
| Generate | `/generate/` |
| Live job | `/generate/live/<job_id>` |
| Runs | `/runs/` |
| Validation | `/validation/` |
| Repairs | `/repairs/` |
| Learning | `/learning/` |
| Registry | `/registry/` |
| Prompts | `/prompts/` |
| Documents | `/documents/` |
| Exports | `/exports/` |
| Settings | `/settings/` |
| Audit | `/audit/` |
| System | `/system/` |
| Health | `/healthz` (public) |

### API

- `GET /api/jobs/<job_id>/status`
- `GET /api/runs/<run_id>/status`
- `GET /generate/api/jobs/<job_id>/status`

Polling only returns operational job status — no model chain-of-thought.

## SQLite UI tables

Shared DB (`SQLITE_DB_PATH`). Defensive `CREATE IF NOT EXISTS`:

| Table | Role |
|-------|------|
| `ui_config` | Effective UI settings |
| `ui_config_versions` | Setting change history |
| `candidate_profiles` | Operator-maintained facts |
| `candidate_profile_versions` | Candidate history |
| `prompt_versions` | Prompt DRAFT/ACTIVE/ARCHIVED |
| `document_templates` | Named export templates |
| `audit_events` | Operator audit log |
| `ui_jobs` | Async generation job state |
| `blueprint_versions` | Immutable blueprint versions |

## Configuration priority

```text
code default → environment (RESUME_UI_*) → saved UI config → run-level override
```

Classifications:

- **SAFE** — variant count, model, export toggles, fonts
- **ADVANCED** — scoring / similarity / repair thresholds (validated ranges)
- **LOCKED** — technology firewall, candidate truthfulness, River active mode

LOCKED keys cannot be mutated via Settings UI or `set_setting`.

## Generation jobs

`generation_service` queues work into `ui_jobs` and runs Phase 2 via an
in-process `ThreadPoolExecutor`. Statuses: `QUEUED`, `RUNNING`, `COMPLETED`,
`FAILED`, `CANCEL_REQUESTED`. Each job uses a unique `run_id` and storage tree.

## Security

- Session auth when `RESUME_ENGINE_UI_PASSWORD` is set
- CSRF on all state-changing POSTs
- Safe-next redirect allowlist
- Path containment for exports / artifact downloads
- API keys never returned to browser (CONFIGURED / NOT CONFIGURED only)
- No stack traces in default error pages
- No shell execution from UI inputs

## River

Learning Center displays shadow metrics and evaluation. Actions allowed:

- Refresh evaluation
- Write evaluation report
- Replay dry run
- Historical train (confirmation required)

**Not allowed:** enabling River active production mode (service raises
`PermissionError`; UI shows Gate 2 lock message).

## Non-goals

- No React/Node SPA
- No Redis/Celery requirement
- No job-application automation
- No engine redesign
- No silent scoring changes
