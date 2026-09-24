"""Phase 3.3 JD intelligence analyzer.

The analyzer deliberately does not fetch URLs or run browser automation. It
accepts raw pasted JD text, applies deterministic parsers, optionally merges
existing blueprint/OpenAI/Laya outputs supplied by callers, and returns a
versioned intelligence JSON document plus common DB filter columns.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from resume_engine.jd_intelligence.clearance_parser import parse_clearance
from resume_engine.jd_intelligence.date_parser import parse_dates
from resume_engine.jd_intelligence.education_parser import parse_education
from resume_engine.jd_intelligence.employment_parser import parse_employment
from resume_engine.jd_intelligence.experience_parser import parse_experience
from resume_engine.jd_intelligence.location_parser import parse_location
from resume_engine.jd_intelligence.requisition_parser import parse_requisition
from resume_engine.jd_intelligence.salary_parser import parse_salary
from resume_engine.jd_intelligence.schema import (
    JOB_INTELLIGENCE_SCHEMA_VERSION,
    build_base_intelligence,
    field,
    now_iso,
    raw_value,
)
from resume_engine.jd_intelligence.work_auth_parser import parse_work_auth
from resume_engine.jd_intelligence.work_mode_parser import (
    parse_relocation,
    parse_shift,
    parse_travel,
    parse_work_mode,
)


def jd_hash(raw_jd_text: str) -> str:
    return hashlib.sha256((raw_jd_text or "").encode("utf-8")).hexdigest()[:32]


def _first_line_title(raw_jd_text: str) -> str | None:
    for line in (raw_jd_text or "").splitlines():
        item = line.strip(" -:\t")
        if not item:
            continue
        if len(item) <= 90 and not re.search(r"\b(salary|location|about|responsibilities)\b", item, re.IGNORECASE):
            return item
    return None


def _classify_family(raw_jd_text: str, blueprint: dict[str, Any] | None = None) -> dict[str, Any]:
    from resume_engine.ui.services.laya_service import classify_jd_role

    job = (blueprint or {}).get("job") or {}
    primary = job.get("primary_family")
    secondary = job.get("secondary_family")
    target_role = job.get("target_title") or _first_line_title(raw_jd_text)
    seniority = job.get("seniority")
    laya_role = classify_jd_role(raw_jd_text, title=target_role)
    role_type = "UNKNOWN"
    text = raw_jd_text or ""
    if not primary:
        primary = laya_role.get("primary_family")
    if not secondary:
        secondary = laya_role.get("secondary_family")
    if not seniority:
        seniority = laya_role.get("seniority") or "mid"
    if re.search(r"\bmanager|manage a team|direct reports\b", text, re.IGNORECASE):
        role_type = "PEOPLE_MANAGER"
    else:
        role_type = "INDIVIDUAL_CONTRIBUTOR"
    primary_source = "OPENAI" if job.get("primary_family") else laya_role.get("source")
    secondary_source = "OPENAI" if job.get("secondary_family") else laya_role.get("source")
    seniority_source = "OPENAI" if job.get("seniority") else laya_role.get("source")
    return {
        "primary_family": field(primary, source=primary_source, evidence=target_role) if primary else field(None, status="NOT_STATED", evidence=[]),
        "secondary_family": field(secondary, source=secondary_source, status="EXPLICIT" if secondary else "NOT_STATED", evidence=target_role),
        "hybrid_probability": job.get("hybrid_probability"),
        "target_role": field(target_role, source="OPENAI" if job.get("target_title") else "DETERMINISTIC", evidence=target_role),
        "normalized_role": target_role,
        "seniority": field(seniority, source=seniority_source, evidence=target_role),
        "role_type": field(role_type, evidence=target_role),
        "people_management_required": True if role_type == "PEOPLE_MANAGER" else None,
        "direct_reports_min": None,
        "direct_reports_max": None,
        "management_experience_years": None,
    }


def _skills_and_responsibilities(raw_jd_text: str, blueprint: dict[str, Any] | None = None) -> dict[str, Any]:
    blueprint = blueprint or {}
    skills = blueprint.get("priority_skills") or blueprint.get("skills") or {}
    responsibilities = blueprint.get("responsibilities") or []
    if isinstance(responsibilities, str):
        responsibilities = [item.strip() for item in responsibilities.split(";") if item.strip()]
    text = raw_jd_text or ""
    explicit_tools = []
    for tool in [
        "OpenAI", "Azure OpenAI", "Anthropic Claude", "Gemini", "LangChain",
        "LlamaIndex", "Hugging Face", "Bedrock", "Vertex AI", "PyTorch",
        "TensorFlow", "AWS", "Azure", "GCP", "Python", "SQL",
    ]:
        if re.search(rf"\b{re.escape(tool)}\b", text, re.IGNORECASE):
            explicit_tools.append(tool)
    programming = [t for t in explicit_tools if t in {"Python", "SQL"}]
    cloud = [t for t in explicit_tools if t in {"AWS", "Azure", "GCP"}]
    ai_tools = [t for t in explicit_tools if t not in {"Python", "SQL", "AWS", "Azure", "GCP"}]
    return {
        "priority_skills": {
            "P1": skills.get("P1") or skills.get("p1") or [],
            "P2": skills.get("P2") or skills.get("p2") or [],
            "P3": skills.get("P3") or skills.get("p3") or [],
            "P4": skills.get("P4") or skills.get("p4") or [],
        },
        "programming_languages": programming,
        "frameworks": [],
        "cloud_platforms": cloud,
        "data_platforms": [],
        "databases": [],
        "devops_tools": [],
        "ai_ml_tools": ai_tools,
        "bi_tools": [],
        "security_tools": [],
        "testing_tools": [],
        "operating_systems": [],
        "other_technologies": [t for t in explicit_tools if t not in set(programming + cloud + ai_tools)],
        "ai_tools": [t for t in ai_tools if t in {"OpenAI", "Azure OpenAI", "Anthropic Claude", "Gemini", "LangChain", "LlamaIndex", "Hugging Face", "Bedrock", "Vertex AI"}],
        "responsibilities": responsibilities,
        "core_responsibilities": responsibilities,
        "architecture_responsibilities": [],
        "coding_responsibilities": [],
        "leadership_responsibilities": [],
        "stakeholder_responsibilities": [],
        "client_responsibilities": [],
        "mentoring_responsibilities": [],
        "production_support_responsibilities": [],
        "documentation_responsibilities": [],
        "compliance_responsibilities": [],
    }


def _certifications(blueprint: dict[str, Any] | None = None) -> dict[str, Any]:
    certs = (blueprint or {}).get("certifications") or []
    return {
        "certifications_required": certs if isinstance(certs, list) else [],
        "certifications_preferred": [],
        "licenses_required": [],
        "licenses_preferred": [],
    }


def _quality_flags(intel: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    if raw_value(intel.get("city")) is None and raw_value(intel.get("state")) is None and raw_value(intel.get("country")) is None:
        flags.append("MISSING_LOCATION")
    if intel.get("location_needs_review"):
        flags.append("LOCATION_NEEDS_REVIEW")
    if raw_value(intel.get("salary_status")) != "STATED":
        flags.append("MISSING_SALARY")
    if raw_value(intel.get("authorization_requirement")) == "NONE_STATED":
        flags.append("WORK_AUTH_NOT_STATED")
    if raw_value(intel.get("employment_type")) == "UNKNOWN":
        flags.append("EMPLOYMENT_TYPE_UNKNOWN")
    if raw_value(intel.get("work_mode")) == "UNKNOWN":
        flags.append("WORK_MODE_UNKNOWN")
    if not intel.get("company"):
        flags.append("MISSING_COMPANY")
    if not raw_value(intel.get("target_role")):
        flags.append("MISSING_TITLE")
    if not intel.get("responsibilities"):
        flags.append("MISSING_RESPONSIBILITIES")
    return flags


def analyze_text(
    raw_jd_text: str,
    *,
    job_id: str | None = None,
    company: str | None = None,
    location: str | None = None,
    source: str | None = None,
    job_url: str | None = None,
    title: str | None = None,
    blueprint: dict[str, Any] | None = None,
    openai_extraction: dict[str, Any] | None = None,
    laya_output: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw_hash = jd_hash(raw_jd_text)
    intel = build_base_intelligence(raw_jd_text, raw_hash)
    intel.update({
        "job_id": job_id,
        "company": company,
        "source": source or "manual",
        "job_url": job_url,
        "title": title or _first_line_title(raw_jd_text),
        "normalized_title": title or _first_line_title(raw_jd_text),
        "business_unit": None,
        "department": None,
        "team": None,
        "posting_status": field("UNKNOWN", status="NOT_STATED", evidence=[]),
    })
    location_text = "\n".join(part for part in [f"Location: {location}" if location else "", raw_jd_text] if part)
    for block in (
        parse_requisition(raw_jd_text),
        parse_dates(raw_jd_text),
        parse_location(location_text),
        parse_work_mode(raw_jd_text),
        parse_relocation(raw_jd_text),
        parse_travel(raw_jd_text),
        parse_employment(raw_jd_text),
        parse_shift(raw_jd_text),
        parse_salary(raw_jd_text),
        parse_work_auth(raw_jd_text),
        parse_clearance(raw_jd_text),
        _classify_family(raw_jd_text, blueprint),
        parse_experience(raw_jd_text),
        parse_education(raw_jd_text),
        _certifications(blueprint),
        _skills_and_responsibilities(raw_jd_text, blueprint),
    ):
        intel.update(block)

    intel.update({
        "industry": None,
        "domain": None,
        "product_area": None,
        "customer_type": "UNKNOWN",
        "regulated_domain": [],
        "physical_requirements": [],
        "language_requirements": [],
        "benefits": [],
        "health_insurance": None,
        "retirement_plan": None,
        "pto": None,
        "parental_leave": None,
        "education_reimbursement": None,
        "relocation_assistance": raw_value(intel.get("relocation_status")) in {"OFFERED", "AVAILABLE"},
        "location_constraint": raw_value(intel.get("work_mode")),
        "work_authorization_constraint": raw_value(intel.get("authorization_requirement")),
        "citizenship_constraint": raw_value(intel.get("authorization_requirement")),
        "clearance_constraint": raw_value(intel.get("clearance_status")),
        "degree_constraint": intel.get("required_degree_levels") or [],
        "experience_constraint": raw_value(intel.get("minimum_years_experience")),
        "certification_constraint": intel.get("certifications_required") or [],
        "schedule_constraint": raw_value(intel.get("shift_type")),
        "travel_constraint": intel.get("travel_required"),
        "openai_extraction": openai_extraction or blueprint or {},
        "laya_output": laya_output or {},
    })
    if intel.get("location_needs_review"):
        from resume_engine.ui.services.laya_service import review_location_evidence

        intel["laya_location_review"] = review_location_evidence(
            raw_jd_text,
            city=raw_value(intel.get("city")),
            state=raw_value(intel.get("state")),
            country=raw_value(intel.get("country")),
            reason=intel.get("location_review_reason"),
        )
    intel["quality_flags"] = _quality_flags(intel)
    from resume_engine.ui.services.laya_service import review_job_workflow

    workflow_review = review_job_workflow(
        {
            "title": intel.get("title"),
            "company": company,
            "location": location,
            "job_url": job_url,
            "jd_text": raw_jd_text,
            "primary_family": raw_value(intel.get("primary_family")),
            "secondary_family": raw_value(intel.get("secondary_family")),
            "seniority": raw_value(intel.get("seniority")),
            "minimum_years_experience": raw_value(intel.get("minimum_years_experience")),
            "work_mode": raw_value(intel.get("work_mode")),
            "employment_type": raw_value(intel.get("employment_type")),
            "authorization_requirement": raw_value(intel.get("authorization_requirement")),
            "salary_min": intel.get("salary_min"),
        },
        intel,
    )
    intel["laya_workflow_review"] = workflow_review
    intel["workflow_readiness"] = workflow_review.get("readiness")
    intel["laya_output"] = {
        **(laya_output or {}),
        "workflow_review": workflow_review,
        "location_review": intel.get("laya_location_review"),
    }
    if workflow_review.get("readiness") == "BLOCKED":
        intel["quality_flags"].append("LAYA_WORKFLOW_BLOCKED")
    elif workflow_review.get("human_review_required"):
        intel["quality_flags"].append("LAYA_HUMAN_REVIEW")
    intel["updated_at"] = now_iso()
    return intel


def filter_columns(intel: dict[str, Any]) -> dict[str, Any]:
    return {
        "country": raw_value(intel.get("country")),
        "state": raw_value(intel.get("state")),
        "city": raw_value(intel.get("city")),
        "work_mode": raw_value(intel.get("work_mode")) or "UNKNOWN",
        "employment_type": raw_value(intel.get("employment_type")) or "UNKNOWN",
        "engagement_type": raw_value(intel.get("engagement_type")) or "UNKNOWN",
        "salary_min": intel.get("salary_min"),
        "salary_max": intel.get("salary_max"),
        "salary_currency": intel.get("salary_currency"),
        "salary_period": intel.get("salary_period") or "UNKNOWN",
        "sponsorship_status": raw_value(intel.get("sponsorship_status")) or "SPONSORSHIP_NOT_STATED",
        "authorization_requirement": raw_value(intel.get("authorization_requirement")) or "NONE_STATED",
        "student_visa_status": raw_value(intel.get("student_visa_status")) or "OPT_CPT_NOT_STATED",
        "clearance_status": raw_value(intel.get("clearance_status")) or "NOT_STATED",
        "minimum_years_experience": raw_value(intel.get("minimum_years_experience")),
        "seniority": raw_value(intel.get("seniority")),
        "primary_family": raw_value(intel.get("primary_family")),
        "secondary_family": raw_value(intel.get("secondary_family")),
        "job_intelligence_schema_version": JOB_INTELLIGENCE_SCHEMA_VERSION,
    }


def analyze_job(job_id: str) -> dict[str, Any]:
    """Analyze a persisted UI job by id and return intelligence JSON.

    Persistence is handled by the UI service layer to avoid importing Flask/UI DB
    concerns into parser modules.
    """
    from resume_engine.ui.services import job_service

    job = job_service.get_job(job_id)
    return analyze_text(
        job.get("jd_text") or "",
        job_id=job_id,
        company=job.get("company"),
        location=job.get("location"),
        source=job.get("source"),
        job_url=job.get("job_url"),
        title=job.get("title"),
        blueprint=job_service.load_blueprint(job) or None,
    )
