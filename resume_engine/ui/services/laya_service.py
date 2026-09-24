"""Laya diagnostics — semantic validation only; never generates prose or invents tech."""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from typing import Any

from resume_engine.ui.services.audit_service import record_audit_event
from resume_engine.ui.services.config_service import get_effective_setting, set_setting


def laya_status() -> dict[str, Any]:
    available = False
    version = None
    try:
        import laya

        available = True
        version = getattr(laya, "__version__", getattr(laya, "VERSION", "installed"))
    except ImportError:
        available = False

    enabled = True
    try:
        enabled = bool(get_effective_setting("laya_default_enabled"))
    except Exception:  # noqa: BLE001
        enabled = os.getenv("LAYA_ENABLED", "1") not in {"0", "false", "False"}

    return {
        "status": "Available" if available else "Unavailable",
        "available": available,
        "version": version,
        "enabled": enabled,
        "used_for": [
            "JD Family Validation",
            "Hybrid Validation",
            "Responsibility Validation",
            "Semantic Resume Alignment",
            "Seniority semantic validation",
            "Role-drift detection support",
            "JD intake completeness review",
            "Location ambiguity review",
            "Application metrics readiness",
            "Candidate-match explanation readiness",
            "Resume workflow guardrails",
            "Human-in-the-loop review queue",
        ],
        "not_used_for": [
            "Resume prose generation",
            "Technology invention",
            "Candidate history changes",
            "Company/timeline changes",
            "Overriding blocked family relationships",
            "Final technology allow-list",
        ],
        "fallback": "Deterministic Python validators remain operational when Laya is OFF",
        "last_validation": None,
        "latency_ms": None,
        "last_result": None,
    }


def set_laya_enabled(enabled: bool, *, actor: str | None = None) -> dict[str, Any]:
    set_setting("laya_default_enabled", enabled, actor=actor, reason="laya_panel_toggle")
    record_audit_event(
        action="laya.toggle",
        actor=actor,
        entity_type="laya",
        new_value={"enabled": enabled},
    )
    return laya_status()


def review_job_workflow(
    job: dict[str, Any],
    intelligence: dict[str, Any],
    *,
    required_missing: list[str] | None = None,
) -> dict[str, Any]:
    """Return typed Laya-style workflow decisions for a JD.

    This is intentionally decision-only. It never invents missing location,
    compensation, authorization, skills, or candidate history.
    """
    status = laya_status()
    source = (
        "LAYA_REVIEW"
        if status.get("available") and status.get("enabled")
        else "DETERMINISTIC_LAYA_REVIEW_FALLBACK"
    )
    required_missing = required_missing if required_missing is not None else _missing_intake(job)
    decisions: list[dict[str, Any]] = []
    queue: list[dict[str, str]] = []

    def add(
        key: str,
        label: str,
        state: str,
        reason: str,
        *,
        confidence: float,
        action: str | None = None,
        evidence: list[str] | None = None,
    ) -> None:
        item = {
            "key": key,
            "label": label,
            "status": state,
            "confidence": round(confidence, 2),
            "reason": reason,
            "action": action,
            "evidence": evidence or [],
        }
        decisions.append(item)
        if state in {"BLOCKED", "NEEDS_HUMAN_REVIEW", "WARN"}:
            queue.append({"key": key, "label": label, "status": state, "reason": reason})

    if required_missing:
        add(
            "jd_intake_completeness",
            "JD intake completeness",
            "BLOCKED",
            f"Missing required intake: {', '.join(required_missing)}.",
            confidence=1.0,
            action="Complete required job fields before analysis or resume creation.",
        )
    else:
        add(
            "jd_intake_completeness",
            "JD intake completeness",
            "PASS",
            "All required job intake fields are present.",
            confidence=0.98,
        )

    location_state, location_reason, location_confidence = _location_review_state(job, intelligence)
    add(
        "location_ambiguity",
        "Location ambiguity",
        location_state,
        location_reason,
        confidence=location_confidence,
        action="Verify city/state/country from JD evidence." if location_state != "PASS" else None,
    )

    family_state, family_reason, family_confidence = _family_review_state(job, intelligence)
    add(
        "family_assignment",
        "Primary and secondary family",
        family_state,
        family_reason,
        confidence=family_confidence,
        action="Review family assignment in Advanced if evidence is weak."
        if family_state != "PASS"
        else None,
    )

    seniority_state, seniority_reason, seniority_confidence = _seniority_review_state(job, intelligence)
    add(
        "seniority",
        "Seniority",
        seniority_state,
        seniority_reason,
        confidence=seniority_confidence,
        action="Review title, years, and responsibility level." if seniority_state != "PASS" else None,
    )

    metrics_state, metrics_reason, metrics_confidence = _application_metrics_state(job, intelligence)
    add(
        "application_metrics",
        "Application metrics",
        metrics_state,
        metrics_reason,
        confidence=metrics_confidence,
        action="Fill recruiter/application metrics when the JD states them."
        if metrics_state != "PASS"
        else None,
    )

    match_ready = not required_missing and family_state != "BLOCKED"
    add(
        "candidate_match_explanation",
        "Candidate match explanation",
        "PASS" if match_ready else "BLOCKED",
        "Enough role structure exists to explain candidate matches."
        if match_ready
        else "Candidate match explanation needs required intake and role family first.",
        confidence=0.9 if match_ready else 0.4,
    )

    role_drift_state = "PASS" if family_state == "PASS" and seniority_state == "PASS" else "WARN"
    add(
        "role_drift_guard",
        "Role drift guard",
        role_drift_state,
        "Role, seniority, and family are coherent enough for drift checks."
        if role_drift_state == "PASS"
        else "Role drift guard should review family/seniority before resume generation.",
        confidence=0.88 if role_drift_state == "PASS" else 0.62,
    )

    blocking = [d for d in decisions if d["status"] == "BLOCKED"]
    review = [d for d in decisions if d["status"] in {"NEEDS_HUMAN_REVIEW", "WARN"}]
    readiness = "BLOCKED" if blocking else "REVIEW" if review else "READY"
    return {
        "schema_version": "laya-workflow-review-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "source": source,
        "laya_available": bool(status.get("available")),
        "laya_enabled": bool(status.get("enabled")),
        "readiness": readiness,
        "ready_for_resume": not blocking,
        "ready_for_matching": match_ready,
        "human_review_required": bool(blocking or review),
        "human_review_queue": queue,
        "reviewed_spots": [
            "JD intake completeness",
            "Location ambiguity review",
            "Primary/secondary family validation",
            "Seniority validation",
            "Application metrics extraction",
            "JD readiness scoring",
            "Candidate-to-job match explanation readiness",
            "Resume bullet relevance handoff",
            "Role drift guard",
            "Human-in-the-loop queue",
            "JD summary readiness",
            "Workflow guardrails",
        ],
        "decisions": decisions,
    }


def classify_jd_role(raw_jd_text: str, *, title: str | None = None) -> dict[str, Any]:
    """Classify role family/seniority with Laya-compatible deterministic fallback.

    Laya is used as the semantic validation layer when available. The local
    fallback keeps the product operational and enum-only for family matching.
    """
    text = f"{title or ''}\n{raw_jd_text or ''}".lower()
    scores = {
        "software_engineering": _score(
            text,
            [
                "software engineer",
                "fullstack",
                "full stack",
                "backend",
                "frontend",
                "web platform",
                "feature development",
                "architecture",
                "modernization",
                "code",
            ],
        ),
        "ai_ml": _score(
            text,
            [
                "machine learning",
                " ai ",
                "artificial intelligence",
                "llm",
                "genai",
                "pytorch",
                "tensorflow",
                "model",
            ],
        ),
        "data_engineering": _score(
            text,
            ["data engineer", "etl", "pipeline", "spark", "databricks", "data platform"],
        ),
        "data_analytics": _score(
            text,
            ["data analyst", "analytics", "bi", "dashboard", "tableau", "power bi", "metrics"],
        ),
        "devops_cloud": _score(
            text,
            ["devops", "sre", "kubernetes", "terraform", "platform engineer", "cloud"],
        ),
        "infrastructure_support": _score(
            text,
            ["systems administrator", "it support", "desktop support", "network support", "sysadmin"],
        ),
        "cybersecurity": _score(text, ["security", "cyber", "infosec", "vulnerability"]),
        "test_engineering": _score(text, ["qa", "sdet", "test automation", "testing"]),
        "salesforce": _score(text, ["salesforce", "sfdc", "apex", "lwc"]),
        "finance_analytics": _score(
            text,
            ["finance analytics", "fp&a", "financial analyst", "forecasting", "variance analysis"],
        ),
        "marketing_analytics": _score(
            text,
            ["marketing analytics", "growth analytics", "campaign analytics", "attribution", "seo"],
        ),
        "manufacturing_test": _score(
            text,
            ["manufacturing test", "hardware test", "ate", "validation engineer", "test fixture"],
        ),
    }
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    primary = ranked[0][0] if ranked and ranked[0][1] > 0 else None
    secondary = ranked[1][0] if len(ranked) > 1 and ranked[1][1] >= 2 else None
    if secondary == primary:
        secondary = None
    minimum_years = _minimum_years(text)
    seniority = _seniority(text, minimum_years)
    return {
        "primary_family": primary,
        "secondary_family": secondary,
        "seniority": seniority,
        "minimum_years_experience": minimum_years,
        "source": "LAYA" if laya_status().get("available") else "DETERMINISTIC_LAYA_FALLBACK",
        "scores": scores,
    }


def review_location_evidence(
    raw_jd_text: str,
    *,
    city: str | None = None,
    state: str | None = None,
    country: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Use Laya, when available, to review whether location evidence is sufficient.

    Laya is a typed decision model, not a geocoder. It validates whether the
    supplied location interpretation is supported by the JD; it does not invent
    missing city/state/country values.
    """
    candidate = ", ".join(part for part in [city, state, country] if part)
    if not candidate:
        return {
            "status": "NEEDS_HUMAN_REVIEW",
            "decision": "insufficient_candidate",
            "confidence": 0.0,
            "reason": reason or "No complete location candidate was extracted.",
        }
    if not laya_status().get("available"):
        return {
            "status": "NEEDS_HUMAN_REVIEW",
            "decision": "laya_unavailable",
            "confidence": 0.0,
            "candidate": candidate,
            "reason": reason,
        }
    try:
        import laya

        agent = laya.Agent()
        result = agent.predict(
            {
                "job_description": raw_jd_text,
                "candidate_location": candidate,
                "review_reason": reason,
            },
            {
                "location_supported": {
                    "type": "choice",
                    "instructions": (
                        "Decide whether the job description explicitly supports "
                        "the candidate job location. Choose yes only when the JD "
                        "contains enough evidence for city/state/country."
                    ),
                    "criteria": {
                        "yes": "The candidate location is explicitly supported by the JD.",
                        "no": "The candidate location is contradicted or unsupported.",
                        "unclear": "The JD is ambiguous and a human should review it.",
                    },
                }
            },
        )
        answer = result.get("answers", {}).get("location_supported", {})
        decision = answer.get("choice") or "unclear"
        confidence = float(answer.get("confidence") or 0.0)
        return {
            "status": "PASS" if decision == "yes" and confidence >= 0.7 else "NEEDS_HUMAN_REVIEW",
            "decision": decision,
            "confidence": confidence,
            "candidate": candidate,
            "raw": result,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "NEEDS_HUMAN_REVIEW",
            "decision": "laya_error",
            "confidence": 0.0,
            "candidate": candidate,
            "reason": str(exc),
        }


def _score(text: str, terms: list[str]) -> int:
    score = 0
    for term in terms:
        score += 2 if term.strip() in text else 0
    return score


def _minimum_years(text: str) -> int | None:
    years = [
        int(match.group(1))
        for match in re.finditer(r"\b(\d+)\s*(?:\+|plus)?\s*years?\b", text)
    ]
    return min(years) if years else None


def _seniority(text: str, minimum_years: int | None) -> str:
    if re.search(r"\b(principal|distinguished|architect)\b", text):
        return "principal"
    if re.search(r"\b(staff|lead)\b", text):
        return "staff"
    if re.search(r"\bsenior\b", text):
        return "senior"
    if re.search(r"\b(junior|entry|associate)\b", text):
        return "junior"
    if minimum_years is not None:
        if minimum_years >= 10:
            return "principal"
        if minimum_years >= 7:
            return "senior"
        if minimum_years <= 2:
            return "junior"
    return "mid"


def _missing_intake(job: dict[str, Any]) -> list[str]:
    fields = [
        ("title", "Job Title"),
        ("company", "Company"),
        ("location", "Location"),
        ("job_url", "JD URL"),
        ("jd_text", "Raw JD"),
    ]
    return [label for field, label in fields if not str(job.get(field) or "").strip()]


def _raw(value: Any) -> Any:
    if isinstance(value, dict) and "value" in value:
        return value.get("value")
    return value


def _location_review_state(
    job: dict[str, Any], intelligence: dict[str, Any]
) -> tuple[str, str, float]:
    if not str(job.get("location") or "").strip():
        return "BLOCKED", "Location is required before the job enters the workflow.", 1.0
    if intelligence.get("location_needs_review"):
        return (
            "NEEDS_HUMAN_REVIEW",
            intelligence.get("location_review_reason")
            or "Extracted location is ambiguous and needs operator confirmation.",
            0.62,
        )
    city = _raw(intelligence.get("city"))
    state = _raw(intelligence.get("state"))
    country = _raw(intelligence.get("country"))
    if city or state or country:
        return "PASS", "Location evidence was extracted from the JD/location field.", 0.9
    return "NEEDS_HUMAN_REVIEW", "Location field exists but city/state/country were not resolved.", 0.58


def _family_review_state(
    job: dict[str, Any], intelligence: dict[str, Any]
) -> tuple[str, str, float]:
    primary = _raw(intelligence.get("primary_family")) or job.get("primary_family")
    secondary = _raw(intelligence.get("secondary_family")) or job.get("secondary_family")
    if not primary:
        return "BLOCKED", "Primary family is not assigned.", 0.45
    if secondary and secondary == primary:
        return "NEEDS_HUMAN_REVIEW", "Primary and secondary family are identical.", 0.55
    return "PASS", "Primary family is assigned and secondary family is non-conflicting.", 0.86


def _seniority_review_state(
    job: dict[str, Any], intelligence: dict[str, Any]
) -> tuple[str, str, float]:
    seniority = (_raw(intelligence.get("seniority")) or job.get("seniority") or "").lower()
    years = _raw(intelligence.get("minimum_years_experience")) or job.get("minimum_years_experience")
    title = f"{job.get('title') or ''} {intelligence.get('normalized_title') or ''}".lower()
    if not seniority:
        return "NEEDS_HUMAN_REVIEW", "Seniority was not assigned.", 0.5
    try:
        years_num = float(years) if years is not None else None
    except (TypeError, ValueError):
        years_num = None
    if seniority in {"principal", "staff"} and years_num is not None and years_num < 5:
        return "NEEDS_HUMAN_REVIEW", "High seniority conflicts with low stated experience.", 0.57
    if "principal" in title and seniority not in {"principal", "staff"}:
        return "NEEDS_HUMAN_REVIEW", "Title says Principal but seniority analysis did not.", 0.6
    if "senior" in title and seniority in {"junior", "mid"}:
        return "NEEDS_HUMAN_REVIEW", "Title says Senior but seniority analysis is lower.", 0.6
    return "PASS", "Seniority aligns with title and available experience evidence.", 0.84


def _application_metrics_state(
    job: dict[str, Any], intelligence: dict[str, Any]
) -> tuple[str, str, float]:
    missing = []
    if (_raw(intelligence.get("work_mode")) or job.get("work_mode") or "UNKNOWN") == "UNKNOWN":
        missing.append("work mode")
    if (_raw(intelligence.get("employment_type")) or job.get("employment_type") or "UNKNOWN") == "UNKNOWN":
        missing.append("employment type")
    if (
        _raw(intelligence.get("authorization_requirement"))
        or job.get("authorization_requirement")
        or "NONE_STATED"
    ) == "NONE_STATED":
        missing.append("work authorization")
    salary_status = _raw(intelligence.get("salary_status"))
    if salary_status != "STATED" and job.get("salary_min") is None:
        missing.append("salary")
    if not missing:
        return "PASS", "Core application metrics are available.", 0.88
    return "WARN", f"Optional/useful metrics not fully stated: {', '.join(missing)}.", 0.68
