"""JD workspace service — Phase 1 only; no auto Phase 2."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from resume_engine.config.settings import PROJECT_ROOT, get_ui_artifact_dir
from resume_engine.ui.services.audit_service import record_audit_event

BLUEPRINT_DIR = PROJECT_ROOT / "resume_engine_data" / "blueprints"
DRAFT_DIR = PROJECT_ROOT / "resume_engine" / "storage" / "ui" / "jd_drafts"


def example_jd() -> str:
    sample = PROJECT_ROOT / "sample_jd.txt"
    if sample.exists():
        return sample.read_text(encoding="utf-8")
    return "Senior Cloud Engineer\n\nRequirements: AWS, Terraform, Kubernetes, Python, CI/CD."


def save_draft(text: str, *, name: str = "draft.txt", actor: str | None = None) -> Path:
    DRAFT_DIR.mkdir(parents=True, exist_ok=True)
    path = DRAFT_DIR / name
    path.write_text(text, encoding="utf-8")
    record_audit_event(action="jd.save_draft", actor=actor, entity_type="jd_draft", entity_id=name)
    return path


def list_drafts() -> list[dict[str, Any]]:
    if not DRAFT_DIR.exists():
        return []
    return [
        {"name": p.name, "path": str(p), "mtime": p.stat().st_mtime, "chars": p.stat().st_size}
        for p in sorted(DRAFT_DIR.glob("*.txt"), key=lambda x: x.stat().st_mtime, reverse=True)
    ]


def list_previous_blueprints(limit: int = 50) -> list[dict[str, Any]]:
    if not BLUEPRINT_DIR.exists():
        return []
    items = []
    for path in sorted(BLUEPRINT_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        job = data.get("job") or {}
        items.append({
            "path": str(path),
            "jd_hash": data.get("jd_hash") or path.stem,
            "target_title": job.get("target_title"),
            "primary_family": job.get("primary_family"),
            "mtime": path.stat().st_mtime,
        })
    return items


def _jd_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:32]


def _friendly_analysis_error(exc: Exception) -> str:
    text = str(exc)
    lowered = text.lower()
    if "insufficient_quota" in lowered or "credit_balance_exhausted" in lowered:
        return "OpenAI credits are exhausted; local Laya fallback was used."
    if "api key" in lowered or "authentication" in lowered or "unauthorized" in lowered:
        return "OpenAI key is missing or invalid; local Laya fallback was used."
    if "rate limit" in lowered or "429" in lowered:
        return "OpenAI rate limit was reached; local Laya fallback was used."
    return f"OpenAI analysis unavailable; local Laya fallback was used. Cause: {text[:180]}"


def _dedupe(items: list[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = str(item or "").strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def _sentence_snippets(text: str, *, limit: int = 6) -> list[str]:
    chunks = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    picked: list[str] = []
    for chunk in chunks:
        clean = re.sub(r"\s+", " ", chunk).strip(" -\t")
        if not clean or len(clean) < 18:
            continue
        if re.search(
            r"\b(responsib|design|build|develop|deliver|lead|own|manage|create|support|maintain|implement|collaborate|test|validate|analy[sz]e)\b",
            clean,
            re.IGNORECASE,
        ):
            picked.append(clean[:260])
        if len(picked) >= limit:
            break
    if picked:
        return picked
    for chunk in chunks:
        clean = re.sub(r"\s+", " ", chunk).strip(" -\t")
        if len(clean) >= 18:
            picked.append(clean[:260])
        if len(picked) >= min(limit, 3):
            break
    return picked or ["Use the responsibilities stated in the job description as the resume alignment source."]


def _explicit_technologies(jd_text: str, intelligence: dict[str, Any]) -> list[str]:
    values: list[Any] = []
    for key in (
        "programming_languages",
        "frameworks",
        "cloud_platforms",
        "data_platforms",
        "databases",
        "devops_tools",
        "ai_ml_tools",
        "bi_tools",
        "security_tools",
        "testing_tools",
        "operating_systems",
        "other_technologies",
        "ai_tools",
    ):
        raw = intelligence.get(key) or []
        if isinstance(raw, list):
            values.extend(raw)
    # Deterministic explicit scan. These are only accepted when literally present in the JD.
    known_terms = [
        "Python", "Java", "JavaScript", "TypeScript", "React", "Node.js", "Angular",
        "SQL", "PostgreSQL", "MySQL", "MongoDB", "Snowflake", "Databricks",
        "Spark", "Kafka", "Airflow", "dbt", "Tableau", "Power BI",
        "AWS", "Azure", "GCP", "Kubernetes", "Docker", "Terraform", "Jenkins",
        "GitHub Actions", "CI/CD", "Linux", "Salesforce", "Apex", "LWC",
        "OpenAI", "Azure OpenAI", "Anthropic Claude", "Gemini", "LangChain",
        "LlamaIndex", "Hugging Face", "Bedrock", "Vertex AI", "PyTorch",
        "TensorFlow", "scikit-learn", "Selenium", "Playwright", "Cypress",
    ]
    text = jd_text or ""
    for term in known_terms:
        pattern = rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])"
        if re.search(pattern, text, re.IGNORECASE):
            values.append(term)
    return _dedupe(values)


def _local_blueprint_from_jd(jd_text: str, *, fallback_reason: str) -> tuple[dict[str, Any], Path]:
    from resume_engine.jd_intelligence.job_analyzer import analyze_text
    from resume_engine.jd_intelligence.schema import raw_value

    intelligence = analyze_text(jd_text)
    role = intelligence.get("laya_output", {})
    tech = _explicit_technologies(jd_text, intelligence)
    role_name = str(raw_value(intelligence.get("target_role")) or intelligence.get("title") or "Job").strip()
    primary_family = raw_value(intelligence.get("primary_family")) or "software_engineering"
    secondary_family = raw_value(intelligence.get("secondary_family")) or "none"
    if not secondary_family:
        secondary_family = "none"
    seniority = raw_value(intelligence.get("seniority")) or "mid"
    years = raw_value(intelligence.get("minimum_years_experience"))

    p1 = tech[:5]
    p2 = tech[5:10]
    p3 = tech[10:15]
    # If the JD names no concrete technology, keep the blueprint valid with role-domain
    # terms while making the source explicit. The mandatory intake gate still blocks
    # vague jobs from generation until title/company/location/URL/JD are present.
    if not p1:
        p1 = _dedupe([role_name, str(primary_family).replace("_", " ").title()])[:2]
    allowed = _dedupe(p1 + p2 + p3)
    responsibilities = _sentence_snippets(jd_text)
    entities = [
        {
            "name": name,
            "category": "technology" if name in tech else "role_domain",
            "priority": "P1" if name in p1 else "P2" if name in p2 else "P3",
            "source": "jd_direct" if name in tech else "local_laya_fallback",
            "requirement": "mentioned",
            "evidence": "literal_jd_match" if name in tech else fallback_reason,
            "confidence": 0.8 if name in tech else 0.55,
            "placement": ["technical_skills"] if name in tech else ["summary_context"],
        }
        for name in allowed
    ]
    jd_hash = _jd_hash(jd_text)
    blueprint = {
        "blueprint_version": "1.0",
        "jd_hash": jd_hash,
        "created_at": datetime.now(UTC).isoformat(),
        "analysis_source": "LOCAL_DETERMINISTIC_FALLBACK",
        "fallback_reason": fallback_reason,
        "job": {
            "target_title": role_name,
            "company": intelligence.get("company"),
            "primary_family": primary_family,
            "primary_confidence": 0.72 if primary_family else None,
            "secondary_family": secondary_family,
            "seniority": seniority,
            "seniority_confidence": 0.72,
            "hybrid_probability": role.get("workflow_review", {}).get("confidence", 0.0) or 0.0,
            "minimum_years_experience": years,
        },
        "priority_skills": {"P1": p1, "P2": p2, "P3": p3, "P4": []},
        "entities": entities,
        "responsibilities": responsibilities,
        "domain_terms": _dedupe([role_name, str(primary_family).replace("_", " ")]),
        "certifications": [],
        "generation_contract": {
            "allowed_technologies": allowed,
            "allow_new_llm_skills": False,
            "allowed_sources": ["jd_direct", "candidate_verified", "local_laya_fallback"],
            "rules": [
                "Resume must remain centered on the target JD.",
                "Use only technologies listed in allowed_technologies.",
                "Do not invent missing company, location, dates, credentials, or tools.",
                "Keep local fallback role-domain terms out of experience bullets unless candidate evidence supports them.",
            ],
        },
        "quality_gates": {
            "P1_coverage_min": 1.00,
            "P2_coverage_min": 0.80,
            "unapproved_skill_count_max": 0,
            "duplicate_bullet_count_max": 0,
            "role_drift_allowed": False,
            "technology_drift_allowed": False,
        },
        "job_intelligence": intelligence,
    }
    out_dir = get_ui_artifact_dir() / "local_blueprints"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"local_{jd_hash}.json"
    path.write_text(json.dumps(blueprint, indent=2, sort_keys=True), encoding="utf-8")
    return blueprint, path


def analyze_jd(jd_text: str, *, actor: str | None = None) -> dict[str, Any]:
    """Run Phase 1 only. Does not generate resumes."""
    import jd_blueprint_engine
    from resume_engine.ui.services.config_service import get_effective_setting

    previous_model = os.environ.get("OPENAI_MODEL")
    routed_model = str(get_effective_setting("openai_jd_analysis_model") or "").strip()
    if routed_model:
        os.environ["OPENAI_MODEL"] = routed_model
        jd_blueprint_engine.OPENAI_MODEL = routed_model
    try:
        blueprint, path = jd_blueprint_engine.run_phase_1(jd_text)
        fallback = False
        fallback_reason = None
    except Exception as exc:  # noqa: BLE001
        fallback_reason = _friendly_analysis_error(exc)
        blueprint, path = _local_blueprint_from_jd(jd_text, fallback_reason=fallback_reason)
        fallback = True
    finally:
        if previous_model is None:
            os.environ.pop("OPENAI_MODEL", None)
        else:
            os.environ["OPENAI_MODEL"] = previous_model
    record_audit_event(
        action="jd.analyze",
        actor=actor,
        entity_type="blueprint",
        entity_id=blueprint.get("jd_hash"),
        metadata={
            "path": str(path),
            "analysis_source": blueprint.get("analysis_source", "OPENAI_PHASE_1"),
            "fallback": fallback,
            "fallback_reason": fallback_reason,
        },
    )
    return {
        "blueprint": blueprint,
        "path": str(path),
        "fallback": fallback,
        "fallback_reason": fallback_reason,
    }


def extract_text_from_upload(filename: str, raw: bytes) -> str:
    name = (filename or "").lower()
    if name.endswith((".txt", ".md")):
        return raw.decode("utf-8", errors="replace")
    if name.endswith(".docx"):
        import re
        import zipfile
        from io import BytesIO
        with zipfile.ZipFile(BytesIO(raw)) as zf:
            xml = zf.read("word/document.xml").decode("utf-8", errors="ignore")
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", xml)).strip()
    if name.endswith(".pdf"):
        # Best-effort plain extraction without heavy deps
        text = raw.decode("latin-1", errors="ignore")
        # crude PDF stream text salvage
        parts = []
        for chunk in text.split("BT"):
            if "ET" in chunk:
                parts.append(chunk.split("ET", 1)[0])
        cleaned = " ".join(parts)
        cleaned = "".join(ch if ch.isprintable() or ch in "\n\t" else " " for ch in cleaned)
        return cleaned.strip() or text[:5000]
    raise ValueError("unsupported file type; use .txt, .docx, or .pdf")
