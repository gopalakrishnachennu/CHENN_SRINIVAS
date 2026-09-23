"""Deterministic blueprint-derived features for River (no candidate PII)."""

from __future__ import annotations

from typing import Any

from resume_engine.learning.eligibility import is_hybrid_blueprint
from resume_engine.learning.online.config import FEATURE_SCHEMA_VERSION
from resume_engine.models.jd_blueprint import JDBlueprint

# Fixed vocabularies — never use hash(); unknown → other_* = 1
PRIMARY_FAMILIES = (
    "devops_cloud",
    "data_engineering",
    "ai_ml",
    "data_analytics",
    "test_engineering",
    "infrastructure_support",
    "software_engineering",
    "security",
    "other",
)

SECONDARY_FAMILIES = PRIMARY_FAMILIES + ("none",)

SENIORITIES = ("intern", "junior", "mid", "senior", "staff", "principal", "lead", "other")

PII_KEYS = frozenset(
    {
        "name",
        "candidate_name",
        "email",
        "phone",
        "address",
        "location",
        "linkedin",
        "website",
        "employer",
        "company",
        "ssn",
    }
)

JD_LENGTH_BUCKETS = (
    (0, 500, "short"),
    (500, 2000, "medium"),
    (2000, 5000, "long"),
    (5000, 10**9, "xlarge"),
)


def _one_hot(prefix: str, value: str, vocabulary: tuple[str, ...]) -> dict[str, float]:
    normalized = (value or "other").strip().lower() or "other"
    if normalized not in vocabulary:
        normalized = "other" if "other" in vocabulary else vocabulary[-1]
    return {f"{prefix}_{item}": 1.0 if item == normalized else 0.0 for item in vocabulary}


def _count_entities(blueprint: JDBlueprint, categories: set[str]) -> int:
    return sum(1 for entity in blueprint.entities if entity.category in categories)


def _has_category(blueprint: JDBlueprint, categories: set[str]) -> bool:
    return _count_entities(blueprint, categories) > 0


def _jd_length_bucket(blueprint: JDBlueprint) -> str:
    # Approximate JD size from structured fields only (no raw candidate text).
    length = (
        sum(len(r) for r in blueprint.responsibilities)
        + sum(len(e.name) for e in blueprint.entities)
        + sum(len(t) for skills in blueprint.priority_skills.values() for t in skills)
    )
    for low, high, label in JD_LENGTH_BUCKETS:
        if low <= length < high:
            return label
    return "xlarge"


def build_context_features(blueprint: JDBlueprint) -> dict[str, float]:
    """
    Build stable numeric features for River.

    Only blueprint-derived fields. No candidate/employer PII.
    """
    features: dict[str, float] = {}
    features.update(_one_hot("primary_family", blueprint.job.primary_family, PRIMARY_FAMILIES))
    features.update(
        _one_hot("secondary_family", blueprint.job.secondary_family or "none", SECONDARY_FAMILIES)
    )
    features.update(_one_hot("seniority", blueprint.job.seniority, SENIORITIES))
    features.update(_one_hot("jd_length_bucket", _jd_length_bucket(blueprint), tuple(b[2] for b in JD_LENGTH_BUCKETS)))

    hybrid = is_hybrid_blueprint(blueprint.job.secondary_family, blueprint.job.hybrid_probability)
    features["hybrid_probability"] = float(blueprint.job.hybrid_probability or 0.0)
    features["is_hybrid"] = 1.0 if hybrid else 0.0

    features["p1_count"] = float(len(blueprint.priority_skills.get("P1") or []))
    features["p2_count"] = float(len(blueprint.priority_skills.get("P2") or []))
    features["p3_count"] = float(len(blueprint.priority_skills.get("P3") or []))
    features["p4_count"] = float(len(blueprint.priority_skills.get("P4") or []))

    features["responsibility_count"] = float(len(blueprint.responsibilities))
    features["certification_count"] = float(len(blueprint.certifications))
    features["mandatory_certification_count"] = float(
        sum(1 for c in blueprint.certifications if c.requirement in {"mandatory", "required"})
    )

    features["has_ai_tools"] = 1.0 if _has_category(blueprint, {"ai_tool", "ai_framework"}) else 0.0
    features["has_cloud"] = 1.0 if _has_category(blueprint, {"cloud"}) else 0.0
    features["has_data_platform"] = 1.0 if _has_category(blueprint, {"data_platform"}) else 0.0
    features["has_devops"] = 1.0 if _has_category(blueprint, {"devops"}) else 0.0
    features["has_bi"] = 1.0 if _has_category(blueprint, {"bi_analytics"}) else 0.0
    features["has_testing"] = 1.0 if _has_category(blueprint, {"testing"}) else 0.0
    features["has_security"] = 1.0 if _has_category(blueprint, {"security"}) else 0.0

    features["ai_tool_count"] = float(_count_entities(blueprint, {"ai_tool", "ai_framework"}))
    features["cloud_tool_count"] = float(_count_entities(blueprint, {"cloud"}))
    features["data_platform_count"] = float(_count_entities(blueprint, {"data_platform"}))
    features["database_count"] = float(_count_entities(blueprint, {"database"}))
    features["devops_tool_count"] = float(_count_entities(blueprint, {"devops"}))

    # Structured domain signal only (first domain term one-hot is avoided — use count).
    features["domain_term_count"] = float(len(blueprint.domain_terms or []))

    # Schema marker for versioning (constant).
    features["feature_schema_marker"] = 1.0
    return features


def assert_no_pii(features: dict[str, Any]) -> None:
    lowered = {str(k).lower() for k in features}
    overlap = lowered & PII_KEYS
    if overlap:
        raise AssertionError(f"PII keys leaked into online features: {sorted(overlap)}")
    for key, value in features.items():
        if isinstance(value, str) and "@" in value:
            raise AssertionError(f"Possible email value in feature {key}")


def feature_schema_version() -> str:
    return FEATURE_SCHEMA_VERSION
