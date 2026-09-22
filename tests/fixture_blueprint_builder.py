"""
fixture_blueprint_builder.py — build deterministic JDBlueprint objects
from raw JD fixture .txt files so behavioral tests don't need live OpenAI.

Each fixture uses a known, pre-computed blueprint that mirrors what Phase 1
would produce. This lets the test suite run 100% offline and deterministically.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from resume_engine.models.jd_blueprint import JDBlueprint

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "jds"
ASSERTION_FILE = Path(__file__).resolve().parent / "fixtures" / "expected" / "fixture_assertions.json"


def load_assertions() -> dict[str, dict]:
    return json.loads(ASSERTION_FILE.read_text(encoding="utf-8"))


def _make_blueprint(
    jd_hash: str,
    title: str,
    primary_family: str,
    secondary_family: str,
    hybrid_probability: float,
    p1: list[str],
    p2: list[str],
    p3: list[str],
    p4: list[str],
    responsibilities: list[str],
    certifications: list[str] | None = None,
    domain_terms: list[str] | None = None,
    entities_extra: list[dict[str, Any]] | None = None,
) -> JDBlueprint:
    allowed = p1 + p2 + p3 + p4 + (certifications or [])

    # Build placement rules
    def _placement(priority: str, name: str) -> list[str]:
        ai_hints = {"openai", "claude", "anthropic", "langchain", "langgraph", "bedrock", "vertex", "mosaic"}
        is_ai = any(h in name.lower() for h in ai_hints)
        if priority == "P1":
            base = ["technical_skills", "experience_responsibilities", "professional_summary"]
        elif priority == "P2":
            base = ["technical_skills", "experience_responsibilities"]
        elif priority == "P3":
            base = ["technical_skills", "selected_experience"] if not is_ai else ["technical_skills", "experience_responsibilities"]
        else:
            base = ["technical_skills_optional"]
        return base

    entities = []
    for priority, skills in [("P1", p1), ("P2", p2), ("P3", p3), ("P4", p4)]:
        for skill in skills:
            cat = "ai_tool" if any(h in skill.lower() for h in {"openai", "claude", "anthropic", "langchain", "langgraph", "bedrock", "vertex", "mosaic"}) else "technology"
            entities.append({
                "name": skill,
                "category": cat,
                "priority": priority,
                "source": "jd_direct" if priority in {"P1", "P2"} else "approved_adjacent",
                "requirement": "required" if priority in {"P1", "P2"} else "preferred",
                "evidence": "fixture blueprint",
                "confidence": 1.0,
                "placement": _placement(priority, skill),
                "parent_skill": None,
            })

    if entities_extra:
        entities.extend(entities_extra)

    return JDBlueprint.model_validate({
        "blueprint_version": "1.0",
        "jd_hash": jd_hash,
        "created_at": "2026-09-22T00:00:00+00:00",
        "job": {
            "target_title": title,
            "company": None,
            "primary_family": primary_family,
            "primary_confidence": 0.92,
            "secondary_family": secondary_family,
            "seniority": "senior",
            "seniority_confidence": 0.90,
            "hybrid_probability": hybrid_probability,
        },
        "priority_skills": {"P1": p1, "P2": p2, "P3": p3, "P4": p4},
        "entities": entities,
        "responsibilities": responsibilities,
        "domain_terms": domain_terms or [],
        "certifications": certifications or [],
        "generation_contract": {
            "allowed_technologies": allowed,
            "allow_new_llm_skills": False,
            "allowed_sources": ["jd_direct", "approved_adjacent"],
            "rules": ["Every technology used must exist in allowed_technologies."],
        },
        "quality_gates": {},
    })


# ---------------------------------------------------------------------------
# One blueprint factory per fixture
# ---------------------------------------------------------------------------

def blueprint_01_pure_data_engineer() -> JDBlueprint:
    return _make_blueprint(
        jd_hash="01_pure_data_engineer",
        title="Senior Data Engineer",
        primary_family="data_engineering",
        secondary_family="none",
        hybrid_probability=0.1,
        p1=["Python", "Apache Spark", "Databricks"],
        p2=["SQL", "Delta Lake", "Airflow"],
        p3=["PySpark"],
        p4=["dbt"],
        responsibilities=[
            "Build ETL pipelines",
            "Optimize Spark workloads",
            "Maintain data quality checks",
            "Support warehouse-ready datasets",
        ],
    )


def blueprint_02_pure_devops() -> JDBlueprint:
    return _make_blueprint(
        jd_hash="02_pure_devops",
        title="Senior DevOps Engineer",
        primary_family="devops_cloud",
        secondary_family="none",
        hybrid_probability=0.08,
        p1=["AWS", "Kubernetes", "Terraform"],
        p2=["CI/CD", "Docker", "Helm"],
        p3=["Ansible"],
        p4=["Vault"],
        responsibilities=[
            "Manage cloud infrastructure",
            "Build CI/CD pipelines",
            "Automate deployments with Terraform",
            "Support Kubernetes clusters",
        ],
    )


def blueprint_03_devops_databricks_ai() -> JDBlueprint:
    return _make_blueprint(
        jd_hash="03_devops_databricks_ai_monster",
        title="Senior Cloud Data Platform Engineer",
        primary_family="devops_cloud",
        secondary_family="data_engineering",
        hybrid_probability=0.87,
        p1=["Databricks", "Terraform", "OpenAI API", "Claude API"],
        p2=["AWS", "Kubernetes", "CI/CD", "Python", "Apache Spark"],
        p3=["LangChain"],
        p4=["Delta Lake", "PySpark", "Docker", "Helm"],
        responsibilities=[
            "Manage Databricks platform",
            "Build cloud infrastructure",
            "Automate deployments",
            "Develop Spark workloads",
            "Build automation using OpenAI API and Claude API",
        ],
        domain_terms=["cloud data platform", "generative AI automation"],
    )


def blueprint_04_data_engineer_devops() -> JDBlueprint:
    return _make_blueprint(
        jd_hash="04_data_engineer_devops",
        title="Senior Data Engineer",
        primary_family="data_engineering",
        secondary_family="devops_cloud",
        hybrid_probability=0.72,
        p1=["Databricks", "Apache Spark", "Python"],
        p2=["SQL", "AWS", "Terraform", "CI/CD"],
        p3=["Airflow"],
        p4=["Docker"],
        responsibilities=[
            "Build and maintain Spark data pipelines",
            "Deploy infrastructure on AWS using Terraform",
            "Support CI/CD pipelines for data workloads",
        ],
    )


def blueprint_05_ai_engineer_openai_claude() -> JDBlueprint:
    return _make_blueprint(
        jd_hash="05_ai_engineer_openai_claude",
        title="Senior AI Engineer",
        primary_family="ai_ml",
        secondary_family="none",
        hybrid_probability=0.15,
        p1=["OpenAI API", "Claude API", "Python"],
        p2=["RAG", "vector databases", "embeddings"],
        p3=["LangChain"],
        p4=["FastAPI"],
        responsibilities=[
            "Build RAG pipelines using OpenAI API",
            "Integrate Claude API for structured generation",
            "Design embedding search systems",
        ],
    )


def blueprint_06_devops_openai_claude() -> JDBlueprint:
    return _make_blueprint(
        jd_hash="06_devops_openai_claude",
        title="Senior DevOps Engineer with AI Automation",
        primary_family="devops_cloud",
        secondary_family="ai_ml",
        hybrid_probability=0.68,
        p1=["AWS", "Terraform", "Kubernetes"],
        p2=["CI/CD", "Python", "OpenAI API", "Claude API"],
        p3=["LangChain"],
        p4=["Docker"],
        responsibilities=[
            "Automate cloud infrastructure with Terraform",
            "Build AI-assisted deployment checks using OpenAI API",
            "Integrate Claude API for operational automation",
        ],
    )


def blueprint_07_databricks_genai() -> JDBlueprint:
    return _make_blueprint(
        jd_hash="07_databricks_genai",
        title="Data Platform + GenAI Engineer",
        primary_family="data_engineering",
        secondary_family="ai_ml",
        hybrid_probability=0.74,
        p1=["Databricks", "Apache Spark", "OpenAI API"],
        p2=["Delta Lake", "Python", "RAG"],
        p3=["LangChain"],
        p4=["PySpark"],
        responsibilities=[
            "Build Databricks-based data pipelines",
            "Develop RAG systems using OpenAI API",
            "Integrate generative AI into data workflows",
        ],
    )


def blueprint_08_unknown_ai_tool() -> JDBlueprint:
    # Contains novel/unknown AI tools — must be preserved in allowed list
    return _make_blueprint(
        jd_hash="08_unknown_ai_tool",
        title="AI Infrastructure Engineer",
        primary_family="ai_ml",
        secondary_family="devops_cloud",
        hybrid_probability=0.65,
        p1=["Python", "PromptMeshX", "VectorFlow Cloud"],
        p2=["Kubernetes", "AWS"],
        p3=["FastAPI"],
        p4=["Docker"],
        responsibilities=[
            "Deploy PromptMeshX AI services on Kubernetes",
            "Build VectorFlow Cloud ingestion pipelines",
            "Support AI infrastructure on AWS",
        ],
    )


def blueprint_09_many_technologies() -> JDBlueprint:
    return _make_blueprint(
        jd_hash="09_many_technologies",
        title="Principal Cloud Data Platform Engineer",
        primary_family="devops_cloud",
        secondary_family="data_engineering",
        hybrid_probability=0.80,
        p1=["AWS", "Kubernetes", "Terraform", "Databricks", "OpenAI API"],
        p2=["Azure", "GCP", "CI/CD", "Python", "Apache Spark", "Snowflake", "Claude API"],
        p3=["Airflow", "dbt", "LangChain", "Helm"],
        p4=["Delta Lake", "PySpark", "Docker", "Vault", "Ansible", "Grafana"],
        responsibilities=[
            "Architect multi-cloud data infrastructure",
            "Manage Databricks and Snowflake platforms",
            "Automate deployments across AWS, Azure, GCP",
            "Integrate AI tooling for operational support",
        ],
    )


def blueprint_10_conflicting_title() -> JDBlueprint:
    # Title says "Data Scientist" but responsibilities are DevOps — follow responsibilities
    return _make_blueprint(
        jd_hash="10_conflicting_title_responsibilities",
        title="Senior DevOps Engineer",  # resolved from responsibilities
        primary_family="devops_cloud",
        secondary_family="none",
        hybrid_probability=0.12,
        p1=["Terraform", "Kubernetes", "AWS"],
        p2=["CI/CD", "Docker", "Helm"],
        p3=["Ansible"],
        p4=["Vault"],
        responsibilities=[
            "Manage Kubernetes clusters",
            "Automate infrastructure with Terraform",
            "Build CI/CD pipelines",
        ],
    )


def blueprint_11_very_long_jd() -> JDBlueprint:
    return _make_blueprint(
        jd_hash="11_very_long_jd",
        title="Senior Data Platform Engineer",
        primary_family="data_engineering",
        secondary_family="devops_cloud",
        hybrid_probability=0.76,
        p1=["Databricks", "Apache Spark", "Python"],
        p2=["AWS", "SQL", "Terraform", "Kubernetes", "CI/CD", "Airflow"],
        p3=["Delta Lake", "dbt"],
        p4=["PySpark", "Docker"],
        responsibilities=[
            "Build and scale Spark data pipelines on Databricks",
            "Deploy AWS infrastructure with Terraform",
            "Operate CI/CD workflows for data engineering teams",
            "Support Airflow orchestration for production workloads",
        ],
    )


def blueprint_12_sparse_poor_jd() -> JDBlueprint:
    return _make_blueprint(
        jd_hash="12_sparse_poor_jd",
        title="Software Engineer",
        primary_family="other",
        secondary_family="none",
        hybrid_probability=0.05,
        p1=["Python"],
        p2=[],
        p3=[],
        p4=[],
        responsibilities=["Write code. Fix bugs."],
    )


def blueprint_13_mandatory_certification() -> JDBlueprint:
    return _make_blueprint(
        jd_hash="13_mandatory_certification",
        title="Senior Cloud Engineer",
        primary_family="devops_cloud",
        secondary_family="none",
        hybrid_probability=0.10,
        p1=["AWS", "Terraform", "Kubernetes"],
        p2=["CI/CD", "Docker"],
        p3=["Helm"],
        p4=["Vault"],
        responsibilities=[
            "Architect AWS cloud infrastructure",
            "Deploy Terraform modules",
            "Manage Kubernetes clusters",
        ],
        certifications=["AWS Certified Solutions Architect"],
    )


def blueprint_14_preferred_certification() -> JDBlueprint:
    return _make_blueprint(
        jd_hash="14_preferred_certification",
        title="Senior Data Engineer",
        primary_family="data_engineering",
        secondary_family="none",
        hybrid_probability=0.08,
        p1=["Databricks", "Spark", "Python"],
        p2=["SQL", "Delta Lake"],
        p3=["Airflow"],
        p4=["dbt"],
        responsibilities=[
            "Build production Databricks pipelines",
            "Optimize Spark workloads",
            "Support data quality frameworks",
        ],
        certifications=["Databricks Data Engineer Associate"],
    )


def blueprint_15_ai_tool_p1_responsibility() -> JDBlueprint:
    return _make_blueprint(
        jd_hash="15_ai_tool_p1_responsibility",
        title="Senior AI Platform Engineer",
        primary_family="ai_ml",
        secondary_family="devops_cloud",
        hybrid_probability=0.70,
        p1=["OpenAI API", "Claude API", "Python"],
        p2=["AWS", "CI/CD"],
        p3=["LangChain"],
        p4=["FastAPI"],
        responsibilities=[
            "Build production systems using OpenAI API",
            "Integrate Claude API for structured generation workflows",
            "Deploy AI services on AWS CI/CD pipelines",
        ],
    )


# ---------------------------------------------------------------------------
# Registry: fixture_id -> (blueprint_factory, assertions_key)
# ---------------------------------------------------------------------------

FIXTURE_BLUEPRINTS: dict[str, callable] = {
    "01_pure_data_engineer": blueprint_01_pure_data_engineer,
    "02_pure_devops": blueprint_02_pure_devops,
    "03_devops_databricks_ai_monster": blueprint_03_devops_databricks_ai,
    "04_data_engineer_devops": blueprint_04_data_engineer_devops,
    "05_ai_engineer_openai_claude": blueprint_05_ai_engineer_openai_claude,
    "06_devops_openai_claude": blueprint_06_devops_openai_claude,
    "07_databricks_genai": blueprint_07_databricks_genai,
    "08_unknown_ai_tool": blueprint_08_unknown_ai_tool,
    "09_many_technologies": blueprint_09_many_technologies,
    "10_conflicting_title_responsibilities": blueprint_10_conflicting_title,
    "11_very_long_jd": blueprint_11_very_long_jd,
    "12_sparse_poor_jd": blueprint_12_sparse_poor_jd,
    "13_mandatory_certification": blueprint_13_mandatory_certification,
    "14_preferred_certification": blueprint_14_preferred_certification,
    "15_ai_tool_p1_responsibility": blueprint_15_ai_tool_p1_responsibility,
}


def get_blueprint(fixture_id: str) -> JDBlueprint:
    factory = FIXTURE_BLUEPRINTS.get(fixture_id)
    if factory is None:
        raise KeyError(f"No blueprint factory for fixture: {fixture_id}")
    return factory()


def all_fixture_ids() -> list[str]:
    return list(FIXTURE_BLUEPRINTS.keys())
