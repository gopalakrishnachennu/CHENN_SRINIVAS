# Phase 3.2 — Product UI Redesign

## Overview

Redesigned the Phase 3.1 Flask/Jinja UI around the actual product model.
Phase 1, Phase 2, validators, repair, River, and export services are untouched.

## Product Model

| Concept | What it stores |
|---------|---------------|
| **Candidate** | Name/contact + primary/secondary job family (from Family Registry, no free text) + companies with start/end dates + optional education/certs. NO titles, skills, bullets, summary, projects. |
| **Job** | JD library entry with Phase 1 analysis. Normal UI shows role, seniority, families, must-have, preferred, responsibilities, certs. Advanced Analysis shows P1–P4 tiers and raw JSON. |
| **Match** | Deterministic family matching: DIRECT / HYBRID / SECONDARY / COMPATIBLE / NO_MATCH. Laya may validate ambiguous classifications but cannot override blocked relationships. |
| **Resume** | Created via wizard: candidate → matched JDs only → options → GENERATE (async, reuses `generation_service`). Library + progress pages with friendly status; technical details under View Details / Advanced. |

## Navigation

### Primary (always visible)
- Dashboard
- **CREATE RESUME** (CTA button)
- Candidates
- Jobs
- Matches
- Resumes

### Advanced (collapsed by default)
- Families
- Blueprints
- Strategies
- Validation
- Repairs
- Laya
- Learning
- Technology Registry
- Prompts
- Settings
- Audit
- System

JD Workspace, Generate, and Runs are removed from primary nav but kept as legacy routes for backward compatibility.

## Routes

### Primary
| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Dashboard |
| GET/POST | `/create/` | Create Resume wizard (single-page) |
| GET | `/create/jobs/<id>` | Step 2 redirect |
| GET/POST | `/create/options/<cid>/<jid>` | Step 3 redirect |
| GET | `/create/progress/<job_id>` | Generation progress |
| GET | `/candidates/` | Candidate list |
| GET/POST | `/candidates/new` | New candidate |
| GET | `/candidates/<id>` | View candidate |
| GET/POST | `/candidates/<id>/edit` | Edit candidate |
| GET | `/jobs/` | Job library |
| GET/POST | `/jobs/new` | Analyze new JD |
| GET/POST | `/jobs/analyze` | Alias for /jobs/new |
| GET | `/jobs/<id>` | Job detail (normal + advanced toggle) |
| GET | `/matches/` | Match explorer |
| GET | `/resumes/` | Resume library |
| GET | `/resumes/<run_id>` | Resume detail |

### Advanced
| Method | Path | Description |
|--------|------|-------------|
| GET | `/advanced/families/` | Family Registry |
| GET/POST | `/advanced/families/<id>` | Edit family |
| GET | `/advanced/laya/` | Laya diagnostics |
| GET | `/blueprints/` | Blueprint list |
| GET | `/strategies/` | Strategy list |
| GET | `/validation/` | Validation reports |
| GET | `/repairs/` | Repair reports |
| GET | `/learning/` | Learning dashboard |
| GET | `/registry/` | Technology Registry |
| GET | `/prompts/` | Prompt Manager |
| GET/POST | `/settings/` | UI settings |
| GET | `/audit/` | Audit log |
| GET | `/system/` | System info |

### Legacy (kept, not in nav)
| Method | Path | Description |
|--------|------|-------------|
| GET/POST | `/jd/` | Old JD Workspace |
| GET/POST | `/generate/` | Old Generate page |
| GET | `/runs/` | Old Runs list |

## DB Schema Extensions

New tables added to the shared SQLite (create-if-not-exists):

- **`family_registry`** — job family definitions with aliases, compatible/hybrid/blocked lists
- **`jd_library`** — analysed JDs with families, seniority, blueprint path
- **`match_cache`** — deterministic match results (candidate_id, job_id, match_type, score)
- **`resume_library`** — generated resume tracking with provenance
- **`resume_runs`** — run-level tracking linking candidates to jobs

The 12 default families (AI/ML, Data Engineering, Data Analytics, DevOps/Cloud, etc.) are auto-seeded on first startup.

## New Services

| Service | Purpose |
|---------|---------|
| `family_registry_service` | CRUD for family registry, resolve aliases, display names |
| `job_service` | Wraps Phase 1 into JD library, search/filter, blueprint loading |
| `match_service` | Deterministic DIRECT/HYBRID/SECONDARY/COMPATIBLE/NO_MATCH rules |
| `create_resume_service` | Wizard flow wrapping `generation_service`, resume library CRUD |
| `laya_service` | Laya toggle and status |

## Provenance

- Company names and dates: `VERIFIED_CANDIDATE_INPUT`
- Role titles in generated resumes: `GENERATED_ROLE_POSITIONING`
- Visible in Advanced view on candidate detail and resume detail pages

## Constraints Preserved

- ✅ River active mode locked (PermissionError on enable attempt)
- ✅ CSRF protection on all mutations
- ✅ Auth required when RESUME_ENGINE_UI_PASSWORD is set
- ✅ Path security via `resolve_validated_resume_path`
- ✅ Phase 1/2/validators/repair/River/export untouched

## How to Start

```bash
python3 -m resume_engine.ui.app
# or
python3 -c "from resume_engine.ui.app import main; main()"
```

Default: http://127.0.0.1:8765

## Tests

```bash
python3 -m pytest tests/ui/ -v
```

34 tests passing (including 11 new product UI tests).
