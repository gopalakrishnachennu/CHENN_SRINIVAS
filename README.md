# Resume Engine

This workspace now has two pure Python phases:

```text
Phase 1:
Job Description
  -> OpenAI exact extraction
  -> Laya role / hybrid / seniority / priority reasoning
  -> Skill registry learning
  -> Adjacent-skill firewall
  -> JD_BLUEPRINT.json
  -> STOP
```

```text
Phase 2:
JD_BLUEPRINT.json
  -> Resume Strategy Engine
  -> Variant Planner
  -> OpenAI Resume Generator
  -> Structured Resume JSON
  -> Hallucination Firewall
  -> Laya Semantic Validator
  -> ATS / Rule Validator
  -> Quality Score
  -> Pass / Targeted Repair
  -> Final Resume JSON
  -> Learning + Reports
```

DOCX/PDF is intentionally not included yet.

## Where To Paste Your OpenAI Key

Paste your key in:

```text
.env.local
```

Replace this line:

```text
OPENAI_API_KEY=PASTE_YOUR_OPENAI_KEY_HERE
```

with:

```text
OPENAI_API_KEY=your_real_key_here
```

Do not paste your key into chat.

## Where To Paste The JD

Paste the complete job description in:

```text
phase_1_jd_intelligence_blueprint.py
```

Replace:

```python
JD_TEXT = """
PASTE THE COMPLETE JOB DESCRIPTION HERE
"""
```

with the complete JD.

Output JSON files are saved to:

```text
resume_engine_data/blueprints/
```

## Run Phase 1

```bash
python3 -m pip install -r requirements.txt
python3 phase_1_jd_intelligence_blueprint.py
```

You can also run from a separate JD text file:

```bash
python3 jd_blueprint_engine.py --jd-file path/to/job_description.txt
```

## Prepare Candidate Profile For Phase 2

Edit:

```text
candidate_profile.json
```

Use truthful candidate facts only. The Phase 2 generator is instructed not to invent employers, dates, certifications, metrics, tools, or responsibilities.

## Run Phase 2

Use the blueprint created by Phase 1:

```bash
python3 phase_2_resume_pipeline.py \
  --blueprint resume_engine_data/blueprints/YOUR_BLUEPRINT.json \
  --candidate-profile candidate_profile.json \
  --variants 5 \
  --audit
```

For a faster first smoke test without Laya:

```bash
python3 phase_2_resume_pipeline.py \
  --blueprint resume_engine_data/blueprints/YOUR_BLUEPRINT.json \
  --candidate-profile candidate_profile.json \
  --variants 1 \
  --skip-laya \
  --audit
```

Phase 2 outputs are saved under:

```text
resume_engine/storage/
```

Important report outputs:

```text
resume_engine/storage/reports/IMPLEMENTATION_AUDIT.json
resume_engine/storage/reports/IMPLEMENTATION_AUDIT.txt
resume_engine/storage/reports/*_validation.json
resume_engine/storage/reports/*_validation.txt
```

## Run Phase 2.5 Behavioral Hardening Audit

This does not just check that modules exist. It executes fixture-driven behavioral checks for:

- P1/P2 coverage
- AI tool placement
- responsibility coverage
- technology firewall
- provenance blocking
- hybrid-family retention
- role drift
- duplicate bullets
- targeted repair planning
- variant differentiation

```bash
python3 -m resume_engine.reports.behavioral_audit
```

Outputs:

```text
resume_engine/storage/reports/BEHAVIORAL_AUDIT.json
resume_engine/storage/reports/BEHAVIORAL_AUDIT.txt
```

## Main Files

- `phase_1_jd_intelligence_blueprint.py` - main working file where you paste the JD.
- `jd_blueprint_engine.py` - reusable Phase 1 engine.
- `phase_2_resume_pipeline.py` - main Phase 2 runner.
- `resume_seed.json` - default template-mode seed; candidate profile is optional.
- `candidate_profile.json` - editable truthful candidate profile for Phase 2.
- `resume_engine/` - Phase 2 package with strategy, generation, validation, scoring, repair, learning, and reports.
- `.env.local` - local key location.
- `sample_jd.txt` - quick test JD.
- `resume_engine_data/skill_registry.json` - self-improving skill registry created on first run.
- `resume_engine_data/jd_history.jsonl` - history of processed JDs.
