# Phase 3.1 — Control Center User Guide

## Start the UI

```bash
export RESUME_ONLINE_LEARNING_MODE=shadow
# optional auth:
# export RESUME_ENGINE_UI_USERNAME=operator
# export RESUME_ENGINE_UI_PASSWORD=...
python3 phase_3_export.py ui
```

Open `http://127.0.0.1:8765`. Health check: `GET /healthz` (no auth).

Keep River in **shadow**. Do not attempt to enable active production ranking.

---

## Dashboard

Home cards show JD/run counts, validation rate, average scores/coverage,
repair rate, and River shadow metrics. Recent runs table links into run detail.
System status tiles report OpenAI key presence, Laya/River/SQLite/storage/
exporters without making paid OpenAI calls.

---

## Process a JD

1. Open **JD Workspace** (`/jd/`).
2. Paste text, upload `.txt` / `.docx` / `.pdf`, load a previous draft, or use **Load Example**.
3. Click **Analyze JD** (Phase 1 only — does not generate resumes).
4. Review target title, seniority, families, hybrid probability, P1–P4, responsibilities,
   certifications, AI tools, domain terms, allowed technologies.
5. Expand raw extraction JSON if needed. Use **Save Draft** to keep the JD text.

Phase 1 and Phase 2 remain separate.

---

## Edit a blueprint

1. Open **Blueprints**.
2. Select a JD hash / version.
3. Edit title, seniority, families, hybrid probability, P1–P4, responsibilities,
   certifications, allowed technologies, adjacent skills.
4. **Save New Version** — always creates a new immutable version (never silent overwrite).
5. Use Compare / Duplicate / Download JSON as needed.

---

## Candidate profiles

1. Open **Candidates**.
2. Create or edit profiles (name, contact, summary, skills, experience, education,
   certifications, projects).
3. Support: Duplicate, Archive, Import/Export JSON.
4. Profiles are **operator facts only**. Generated resume content is never auto-promoted
   into verified candidate truth.

---

## Strategies

Open **Strategies** with a blueprint selected. Review eligible positioning,
historical and River shadow rankings. Enable/disable eligible strategies and
reorder production positioning within the eligible set only. Variant count can
be adjusted within SAFE config limits.

---

## Generate resumes

1. Open **Generate**.
2. Choose blueprint, mode (`TEMPLATE` / `CANDIDATE`), candidate, variant count,
   model, Laya/repair/export toggles, optional custom run ID.
3. Review the workflow strip (Blueprint → … → Export).
4. Click **START GENERATION**. Work runs asynchronously (job statuses in SQLite).
5. Follow **Live** progress (`/generate/live/<job_id>`) via status polling.

---

## Review runs and variants

- **Runs** list supports filters (date, JD, family, candidate, pass/fail, model, score, run ID).
- Run detail shows JD, blueprint, strategy, variants, raw/repaired/validated/rejected,
  reports, exports, learning, errors.
- Variant tabs highlight P1–P4 skills; unauthorized tech shows warnings.
- Diff views: Raw vs Repaired, Repaired vs Final.
- Actions: Open, Duplicate configuration, Export, Archive (no default delete).

---

## Validation center

**Validation** lists reports with PASS / WARNING / FAIL for coverage, firewall,
P4, AI tools, hybrid retention, duplicates, drift, ATS, Laya, uniqueness, similarity,
and **Internal JD Compatibility Score** (never labeled “Official ATS Score”).

Rejected artifacts cannot be treated as validated downloads.

---

## Repairs

**Repairs** shows failure codes, locations, original/replacement text, scores.
Approve / Reject / Manual edit / Revalidate. Manual edits still go through all
validators; the technology firewall cannot be bypassed in the UI.

---

## River learning (shadow)

**Learning** shows a large warning: Production Control OFF / Mode SHADOW.

View policy/feature/reward versions, observation counts, agreement, rewards,
per-strategy and per-family tables, activation evidence readiness.

Buttons:

- Refresh Evaluation
- Write Evaluation Report
- Replay Dry Run
- Historical Replay Train (requires confirmation)

Display: **ACTIVE MODE LOCKED UNTIL FUTURE GATE**. There is no working control
to turn on River active production ranking.

Observation browser: filter decisions; open a decision for context features,
actions, River ranking, reward components.

---

## Technology registry

Search technologies; add aliases / adjacent links; Approve / Block / Merge.
Edits are audited. Registry changes do **not** globally promote skills into P1–P4
(those remain JD-specific).

---

## Prompt manager

Manage Phase 1, generation, repair, and Laya-related prompts. Every change creates
a version (`DRAFT` / `ACTIVE` / `ARCHIVED`). Create Version, Compare, Activate,
Rollback — never overwrite a previous active prompt in place.

---

## Document designer

Configure fonts, sizes, margins, spacing, accent, page target. Defaults preserve
current exporter behavior. Save named templates (Classic ATS, Modern ATS, Compact
Two Page, Executive). Preview when available. No unsafe tables/graphics in body.

---

## Exports

Filter and download DOCX / PDF / ZIP / Resume JSON / validation / blueprint artifacts
through validated paths only.

---

## Settings

Edit SAFE and ADVANCED settings with range validation. LOCKED settings
(firewall, candidate truth, River active) are display-only.

Each change creates a configuration version (timestamp, old/new, actor, reason).
Use **Rollback Configuration** / Compare Versions.

API key display: `CONFIGURED` or `NOT CONFIGURED` — never the secret itself.
Keys stay in environment / `.env.local`, not SQLite.

---

## Audit and System

**Audit** lists operator actions (login, JD process, edits, generation, exports,
learning replay, etc.) without passwords or API keys.

**System** shows app/git/Python/River/OpenAI/Laya versions, SQLite and storage
paths, policy/feature/reward versions, and health (DB, filesystem, River policy,
exporter) without paid OpenAI probes.

---

## Troubleshooting

- Request timeout on generate → confirm job is queued; use Live status, not synchronous wait.
- 400 on POST → check CSRF token (reload form).
- Auth redirect loop → verify password env vars; `/healthz` stays public.
- Path errors on download → only validated storage-relative paths are allowed.
