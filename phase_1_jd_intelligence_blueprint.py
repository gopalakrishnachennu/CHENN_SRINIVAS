"""
Phase 1: JD Intelligence + Blueprint

Use this file as the main working material.

Before running:
1. Paste your OpenAI key into .env.local
2. Paste the complete JD into JD_TEXT below
3. Run:

   python3 phase_1_jd_intelligence_blueprint.py

This script stops after creating JD_BLUEPRINT.json.
It does not generate resumes.
"""

import json

from jd_blueprint_engine import (
    build_blueprint,
    extract_jd,
    load_environment,
    load_laya_agent,
    load_registry,
    print_blueprint_summary,
    save_blueprint,
    update_registry_from_jd,
)
from openai import OpenAI


# -------------------------------------------------------------------
# PASTE THE COMPLETE JOB DESCRIPTION HERE
# -------------------------------------------------------------------

JD_TEXT = """
Role: Senior AI DevOps & Data Engineer

We are looking for a hybrid DevOps and Data Engineer who can manage cloud infrastructure and build AI-powered pipelines.

Required Skills & Experience:
- AWS, Terraform, and Kubernetes for scalable cloud infrastructure
- Databricks and Apache Spark for large-scale data processing
- Strong Python programming
- Experience integrating LLMs (OpenAI API, Claude) into production workflows
- Building AI agent architectures using LangChain

Responsibilities:
- Deploy and maintain Kubernetes clusters on AWS using Terraform
- Design and optimize Databricks data engineering pipelines with Spark
- Integrate Claude and OpenAI API for automated operational insights
- Develop GenAI features utilizing LangChain
- Ensure platform reliability and observability
"""


def main() -> None:
    if not JD_TEXT.strip() or "PASTE THE COMPLETE JOB DESCRIPTION HERE" in JD_TEXT:
        raise ValueError(
            "Paste the complete job description into JD_TEXT before running Phase 1."
        )

    load_environment()

    client = OpenAI()
    laya_agent = load_laya_agent()
    skill_registry = load_registry()

    # 1. Discover everything explicitly in the JD.
    extraction = extract_jd(JD_TEXT, client)

    # 2. Update persistent skill/tool registry.
    updated_registry = update_registry_from_jd(
        extraction,
        skill_registry,
    )

    # 3. Build locked JD blueprint.
    blueprint = build_blueprint(
        JD_TEXT,
        extraction,
        updated_registry,
        laya_agent,
    )

    # 4. Save it.
    blueprint_path = save_blueprint(blueprint)

    # 5. Show important output.
    print_blueprint_summary(blueprint, blueprint_path)

    print("\nComplete JSON:")
    print(json.dumps(blueprint, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
