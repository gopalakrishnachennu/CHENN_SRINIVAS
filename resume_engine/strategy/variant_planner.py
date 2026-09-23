"""Dynamic, family-aware variant planner (Phase 2.6 Wave 2)."""

from __future__ import annotations

from dataclasses import dataclass

from resume_engine.config import thresholds
from resume_engine.models.jd_blueprint import JDBlueprint
from resume_engine.models.resume_strategy import ResumeStrategy, VariantStrategy
from resume_engine.validation.text_utils import normalize_text


@dataclass(frozen=True)
class AngleTemplate:
    positioning: str
    description: str
    families: tuple[str, ...]
    evidence_terms: tuple[str, ...]
    boost_terms: tuple[str, ...]
    requires_ai: bool = False
    requires_hybrid_secondary: bool = False


ANGLE_LIBRARY: list[AngleTemplate] = [
    # DEVOPS / CLOUD
    AngleTemplate(
        "cloud_infrastructure",
        "Emphasize cloud infrastructure ownership and platform delivery.",
        ("devops_cloud", "infrastructure_support"),
        ("aws", "azure", "gcp", "cloud", "terraform", "kubernetes"),
        ("aws", "azure", "gcp", "terraform", "kubernetes"),
    ),
    AngleTemplate(
        "platform_reliability",
        "Emphasize platform reliability, observability, and operational excellence.",
        ("devops_cloud", "infrastructure_support", "software_engineering"),
        ("reliability", "observability", "kubernetes", "ci/cd", "sre"),
        ("kubernetes", "ci/cd", "terraform", "python"),
    ),
    AngleTemplate(
        "automation_iac",
        "Emphasize automation, IaC, and delivery reliability.",
        ("devops_cloud", "test_engineering", "software_engineering"),
        ("terraform", "ci/cd", "automation", "infrastructure as code", "ansible"),
        ("terraform", "ci/cd", "docker", "helm", "python"),
    ),
    AngleTemplate(
        "container_orchestration",
        "Emphasize container orchestration and Kubernetes platform operations.",
        ("devops_cloud",),
        ("kubernetes", "docker", "helm", "container"),
        ("kubernetes", "docker", "helm"),
    ),
    AngleTemplate(
        "ai_enabled_operations",
        "Emphasize AI-enabled operations using approved AI tools.",
        ("devops_cloud", "infrastructure_support", "data_engineering", "ai_ml"),
        ("openai", "claude", "langchain", "llm", "genai"),
        ("openai api", "claude api", "langchain", "python"),
        requires_ai=True,
    ),
    # DATA ENGINEERING
    AngleTemplate(
        "pipeline_engineering",
        "Emphasize data pipeline engineering and ETL/ELT delivery.",
        ("data_engineering",),
        ("pipeline", "etl", "spark", "airflow", "python"),
        ("apache spark", "python", "airflow", "sql"),
    ),
    AngleTemplate(
        "data_platform_engineering",
        "Emphasize data platform reliability and lakehouse operations.",
        ("data_engineering",),
        ("databricks", "delta lake", "lakehouse", "data platform"),
        ("databricks", "delta lake", "apache spark"),
    ),
    AngleTemplate(
        "spark_databricks_platform",
        "Emphasize Spark/Databricks platform workloads and reliability.",
        ("data_engineering",),
        ("databricks", "spark", "pyspark", "delta lake"),
        ("databricks", "apache spark", "pyspark", "delta lake"),
    ),
    AngleTemplate(
        "orchestration_reliability",
        "Emphasize orchestration, scheduling, and pipeline reliability.",
        ("data_engineering", "devops_cloud"),
        ("airflow", "orchestration", "dag", "ci/cd"),
        ("airflow", "python", "ci/cd"),
    ),
    AngleTemplate(
        "cloud_data_engineering",
        "Emphasize cloud data engineering on approved cloud platforms.",
        ("data_engineering", "devops_cloud"),
        ("aws", "azure", "gcp", "spark", "databricks", "s3"),
        ("aws", "databricks", "apache spark", "python"),
    ),
    # AI
    AngleTemplate(
        "llm_application_engineering",
        "Emphasize LLM application engineering with approved AI tools.",
        ("ai_ml", "software_engineering"),
        ("openai", "claude", "llm", "prompt"),
        ("openai api", "claude api", "python"),
        requires_ai=True,
    ),
    AngleTemplate(
        "ai_platform",
        "Emphasize AI platform integration and operationalization.",
        ("ai_ml", "devops_cloud", "data_engineering"),
        ("langchain", "rag", "embeddings", "vector", "openai", "claude"),
        ("langchain", "openai api", "claude api"),
        requires_ai=True,
    ),
    AngleTemplate(
        "rag_integration",
        "Emphasize RAG and retrieval-augmented application patterns.",
        ("ai_ml", "data_engineering"),
        ("rag", "embeddings", "vector", "retrieval"),
        ("rag", "embeddings", "langchain"),
        requires_ai=True,
    ),
    AngleTemplate(
        "model_integration",
        "Emphasize model/API integration into production workflows.",
        ("ai_ml", "software_engineering", "devops_cloud"),
        ("openai", "claude", "api", "integration"),
        ("openai api", "claude api", "python"),
        requires_ai=True,
    ),
    AngleTemplate(
        "ai_automation",
        "Emphasize AI automation of operational and delivery workflows.",
        ("ai_ml", "devops_cloud", "data_engineering"),
        ("openai", "claude", "automation", "agent"),
        ("openai api", "claude api", "langchain"),
        requires_ai=True,
    ),
    # DATA ANALYTICS
    AngleTemplate(
        "sql_analytics",
        "Emphasize SQL analytics and analytical query delivery.",
        ("data_analytics",),
        ("sql", "analytics", "warehouse", "reporting"),
        ("sql", "python"),
    ),
    AngleTemplate(
        "bi_dashboard",
        "Emphasize BI/dashboard delivery and insight visualization.",
        ("data_analytics",),
        ("tableau", "power bi", "dashboard", "bi"),
        ("tableau", "power bi", "sql"),
    ),
    AngleTemplate(
        "business_insights",
        "Emphasize business insights and stakeholder analytics delivery.",
        ("data_analytics",),
        ("insights", "analytics", "reporting", "kpi"),
        ("sql", "python"),
    ),
    AngleTemplate(
        "data_quality_analytics",
        "Emphasize data quality and trusted analytics foundations.",
        ("data_analytics", "data_engineering"),
        ("data quality", "validation", "sql", "dbt"),
        ("sql", "dbt", "python"),
    ),
    AngleTemplate(
        "analytics_automation",
        "Emphasize analytics automation and repeatable reporting workflows.",
        ("data_analytics",),
        ("automation", "python", "sql", "etl"),
        ("python", "sql"),
    ),
    # TEST ENGINEERING
    AngleTemplate(
        "test_automation",
        "Emphasize test automation and continuous validation.",
        ("test_engineering",),
        ("test automation", "pytest", "selenium", "qa", "ci/cd"),
        ("python", "ci/cd"),
    ),
    AngleTemplate(
        "systems_validation",
        "Emphasize systems validation and end-to-end quality gates.",
        ("test_engineering",),
        ("validation", "systems test", "quality", "verification"),
        ("python", "ci/cd"),
    ),
    AngleTemplate(
        "manufacturing_test",
        "Emphasize manufacturing test and production validation workflows.",
        ("test_engineering",),
        ("manufacturing", "production test", "failure analysis", "yield"),
        ("python", "test"),
    ),
    AngleTemplate(
        "failure_analysis",
        "Emphasize failure analysis and defect triage.",
        ("test_engineering",),
        ("failure analysis", "root cause", "defect", "debug"),
        ("python",),
    ),
    AngleTemplate(
        "test_infrastructure",
        "Emphasize test infrastructure and harness development.",
        ("test_engineering", "devops_cloud"),
        ("test infrastructure", "harness", "ci/cd", "automation"),
        ("python", "ci/cd", "docker"),
    ),
    # INFRASTRUCTURE SUPPORT
    AngleTemplate(
        "systems_operations",
        "Emphasize systems operations and day-2 support.",
        ("infrastructure_support",),
        ("operations", "server", "linux", "support", "incident"),
        ("linux", "python"),
    ),
    AngleTemplate(
        "networking_support",
        "Emphasize networking and connectivity support.",
        ("infrastructure_support",),
        ("network", "firewall", "dns", "vpn"),
        ("network",),
    ),
    AngleTemplate(
        "cloud_support",
        "Emphasize cloud support and managed-service operations.",
        ("infrastructure_support", "devops_cloud"),
        ("aws", "azure", "gcp", "support", "cloud"),
        ("aws", "azure", "gcp"),
    ),
    AngleTemplate(
        "reliability_support",
        "Emphasize reliability and incident response support.",
        ("infrastructure_support", "devops_cloud"),
        ("reliability", "incident", "on-call", "monitoring"),
        ("monitoring", "python"),
    ),
    AngleTemplate(
        "support_automation",
        "Emphasize support automation and runbook tooling.",
        ("infrastructure_support", "devops_cloud"),
        ("automation", "runbook", "scripting", "python"),
        ("python", "bash"),
    ),
    # Generic software fallback angles
    AngleTemplate(
        "backend_service_delivery",
        "Emphasize backend service delivery and API reliability.",
        ("software_engineering",),
        ("api", "backend", "service", "python", "java"),
        ("python", "api"),
    ),
    AngleTemplate(
        "application_reliability",
        "Emphasize application reliability and production support.",
        ("software_engineering", "devops_cloud"),
        ("reliability", "monitoring", "ci/cd", "service"),
        ("ci/cd", "python"),
    ),
]


def _corpus(blueprint: JDBlueprint) -> str:
    parts = [
        blueprint.job.primary_family,
        blueprint.job.secondary_family,
        blueprint.job.target_title or "",
        " ".join(blueprint.domain_terms),
        " ".join(blueprint.responsibilities),
        " ".join(skill for skills in blueprint.priority_skills.values() for skill in skills),
        " ".join(blueprint.generation_contract.allowed_technologies),
    ]
    return normalize_text(" ".join(parts))


def _has_ai_evidence(blueprint: JDBlueprint, corpus: str) -> bool:
    ai_hints = (
        "openai",
        "claude",
        "langchain",
        "langgraph",
        "llm",
        "rag",
        "embeddings",
        "genai",
        "anthropic",
    )
    if any(hint in corpus for hint in ai_hints):
        return True
    return any(
        entity.category in {"ai_tool", "ai_framework"} for entity in blueprint.entities
    )


def _evidence_score(angle: AngleTemplate, corpus: str, blueprint: JDBlueprint) -> float:
    hits = sum(1 for term in angle.evidence_terms if term in corpus)
    if hits == 0:
        return 0.0

    family_bonus = 0.0
    primary = blueprint.job.primary_family
    secondary = blueprint.job.secondary_family
    if primary in angle.families:
        family_bonus += 2.0
    if secondary in angle.families and secondary != "none":
        family_bonus += 1.0

    p1_boost = 0.0
    p1 = {normalize_text(skill) for skill in blueprint.priority_skills.get("P1", [])}
    for term in angle.boost_terms:
        if term in p1 or any(term in skill for skill in p1):
            p1_boost += 0.5

    return hits + family_bonus + p1_boost


def _eligible_angles(blueprint: JDBlueprint) -> list[tuple[float, AngleTemplate]]:
    corpus = _corpus(blueprint)
    ai_ok = _has_ai_evidence(blueprint, corpus)
    hybrid = (
        blueprint.job.secondary_family != "none"
        and blueprint.job.hybrid_probability >= 0.55
    )
    scored: list[tuple[float, AngleTemplate]] = []
    for angle in ANGLE_LIBRARY:
        if angle.requires_ai and not ai_ok:
            continue
        if angle.requires_hybrid_secondary and not hybrid:
            continue
        # Must relate to primary or (if hybrid) secondary family, or have strong corpus hits.
        family_match = blueprint.job.primary_family in angle.families or (
            hybrid and blueprint.job.secondary_family in angle.families
        )
        score = _evidence_score(angle, corpus, blueprint)
        if not family_match and score < 2.0:
            continue
        if score <= 0:
            continue
        scored.append((score, angle))

    scored.sort(key=lambda item: (-item[0], item[1].positioning))
    return scored


def _fallback_angles(blueprint: JDBlueprint) -> list[AngleTemplate]:
    """Deterministic fallback when evidence is sparse — still family-scoped."""
    primary = blueprint.job.primary_family
    corpus = _corpus(blueprint)
    ai_ok = _has_ai_evidence(blueprint, corpus)
    family_angles = [
        angle
        for angle in ANGLE_LIBRARY
        if primary in angle.families and (not angle.requires_ai or ai_ok)
    ]
    if not family_angles:
        family_angles = [
            angle
            for angle in ANGLE_LIBRARY
            if (
                "software_engineering" in angle.families
                or "devops_cloud" in angle.families
            )
            and not angle.requires_ai
        ]
    return family_angles[: thresholds.DEFAULT_VARIANT_COUNT]


def _base_weight(skill: str, blueprint: JDBlueprint) -> float:
    priorities = blueprint.priority_skills
    if skill in priorities.get("P1", []):
        return 1.0
    if skill in priorities.get("P2", []):
        return 0.85
    if skill in priorities.get("P3", []):
        return 0.65
    return 0.35


def _build_emphasis(
    blueprint: JDBlueprint,
    strategy: ResumeStrategy,
    angle: AngleTemplate,
) -> dict[str, float]:
    allowed = strategy.allowed_tools
    emphasis = {skill: _base_weight(skill, blueprint) for skill in allowed}
    for skill in blueprint.priority_skills.get("P1", []):
        emphasis[skill] = 1.0
    for skill in blueprint.priority_skills.get("P2", []):
        emphasis[skill] = max(emphasis.get(skill, 0), 0.9)

    for skill in allowed:
        lowered = normalize_text(skill)
        if any(term in lowered or lowered in term for term in angle.boost_terms):
            emphasis[skill] = max(emphasis.get(skill, 0), 0.95)
    return emphasis


def _apply_historical_ranking(
    scored: list[tuple[float, AngleTemplate]],
    insights: dict,
) -> list[tuple[float, AngleTemplate]]:
    """Re-rank eligible angles using historical successful positionings when sample count allows."""
    from resume_engine.learning.strategy_memory import historical_boost_for_positioning

    if not insights.get("applied"):
        return scored

    rescored = [
        (score + historical_boost_for_positioning(insights, angle.positioning), angle)
        for score, angle in scored
    ]
    rescored.sort(key=lambda item: (-item[0], item[1].positioning))
    return rescored


def list_eligible_positionings(blueprint: JDBlueprint) -> list[str]:
    """Evidence-scored eligible angles (excludes fallback-only labels)."""
    return [angle.positioning for _, angle in _eligible_angles(blueprint)]


def list_all_candidate_positionings(blueprint: JDBlueprint) -> list[str]:
    """
    All positioning labels the deterministic planner can emit before the
    variant-count limit (eligible + family-scoped fallback).

    River may rank only this set — never invent outside it.
    """
    ordered: list[str] = []
    for _, angle in _eligible_angles(blueprint):
        if angle.positioning not in ordered:
            ordered.append(angle.positioning)
    for angle in _fallback_angles(blueprint):
        if angle.positioning not in ordered:
            ordered.append(angle.positioning)
    return ordered


def select_angle_templates(
    blueprint: JDBlueprint,
    variant_count: int | None = None,
    *,
    learning_insights: dict | None = None,
    outcomes_path=None,
) -> list[AngleTemplate]:
    from resume_engine.learning.strategy_memory import retrieve_strategy_insights

    limit = variant_count or thresholds.DEFAULT_VARIANT_COUNT
    insights = learning_insights
    if insights is None:
        insights = retrieve_strategy_insights(blueprint, outcomes_path=outcomes_path)

    scored = _apply_historical_ranking(_eligible_angles(blueprint), insights)
    selected = [angle for _, angle in scored[:limit]]

    if len(selected) < limit:
        for angle in _fallback_angles(blueprint):
            if angle.positioning not in {item.positioning for item in selected}:
                selected.append(angle)
            if len(selected) >= limit:
                break

    # Hybrid: ensure at least one angle from each family when possible.
    if (
        blueprint.job.secondary_family != "none"
        and blueprint.job.hybrid_probability >= 0.55
        and selected
    ):
        primary = blueprint.job.primary_family
        secondary = blueprint.job.secondary_family
        has_primary = any(primary in angle.families for angle in selected)
        has_secondary = any(secondary in angle.families for angle in selected)
        if not has_secondary:
            for score, angle in scored:
                if secondary in angle.families and angle.positioning not in {
                    item.positioning for item in selected
                }:
                    selected[-1] = angle
                    has_secondary = True
                    break
            if not has_secondary:
                for angle in ANGLE_LIBRARY:
                    if secondary in angle.families and not angle.requires_ai:
                        corpus = _corpus(blueprint)
                        if _evidence_score(angle, corpus, blueprint) > 0:
                            selected[-1] = angle
                            break
        _ = has_primary  # primary already preferred by ranking

    return selected[:limit]


def create_variants(
    blueprint: JDBlueprint,
    strategy: ResumeStrategy,
    *,
    learning_insights: dict | None = None,
    outcomes_path=None,
) -> list[VariantStrategy]:
    from resume_engine.learning.strategy_memory import retrieve_strategy_insights

    insights = learning_insights
    if insights is None:
        insights = retrieve_strategy_insights(blueprint, outcomes_path=outcomes_path)

    angles = select_angle_templates(
        blueprint,
        learning_insights=insights,
        outcomes_path=outcomes_path,
    )
    variants: list[VariantStrategy] = []

    for index, angle in enumerate(angles, start=1):
        rules = [
            "Use only P1, P2, P3, and approved P4 technologies.",
            "Change emphasis, not the approved technology universe.",
            "Do not introduce unrelated stacks or role identity drift.",
            f"Embody the variant angle: {angle.positioning}.",
        ]
        if insights.get("applied"):
            rules.append(
                "Historical eligible learning applied "
                f"(n={insights.get('eligible_sample_count')}; "
                f"min={insights.get('min_sample_count')})."
            )
        else:
            rules.append(
                "Deterministic JD strategy "
                f"(eligible history n={insights.get('eligible_sample_count', 0)} "
                f"< min={insights.get('min_sample_count', thresholds.LEARNING_MIN_SAMPLE_COUNT)})."
            )

        emphasis = _build_emphasis(blueprint, strategy, angle)
        # Learning re-ranks angles only; never expand beyond blueprint-allowed tools.
        allowed = set(strategy.allowed_tools)
        if allowed:
            emphasis = {skill: weight for skill, weight in emphasis.items() if skill in allowed}

        variants.append(
            VariantStrategy(
                variant_id=f"V{index:02d}",
                positioning=angle.positioning,
                description=angle.description,
                emphasis=emphasis,
                bullet_bias={
                    "P1": 1.0,
                    "P2": 0.85,
                    "P3": 0.55,
                    "P4": 0.25,
                },
                rules=rules,
            )
        )

    return variants
