from resume_engine.models.jd_blueprint import JDBlueprint
from resume_engine.models.resume_strategy import ResumeStrategy, VariantStrategy


VARIANT_DEFINITIONS = [
    ("V01", "cloud_platform_heavy", "Emphasize cloud platform ownership and infrastructure delivery."),
    ("V02", "databricks_platform_heavy", "Emphasize Databricks platform operations and data platform reliability."),
    ("V03", "devops_automation_heavy", "Emphasize CI/CD, automation, infrastructure as code, and delivery reliability."),
    ("V04", "cloud_data_engineering_heavy", "Emphasize Spark/data engineering on cloud platform foundations."),
    ("V05", "ai_enabled_data_platform_heavy", "Emphasize AI-enabled platform automation using approved AI tools."),
]


def _base_weight(skill: str, blueprint: JDBlueprint) -> float:
    priorities = blueprint.priority_skills
    if skill in priorities.get("P1", []):
        return 1.0
    if skill in priorities.get("P2", []):
        return 0.85
    if skill in priorities.get("P3", []):
        return 0.65
    return 0.35


def create_variants(blueprint: JDBlueprint, strategy: ResumeStrategy) -> list[VariantStrategy]:
    allowed = strategy.allowed_tools
    variants: list[VariantStrategy] = []

    for variant_id, positioning, description in VARIANT_DEFINITIONS:
        emphasis = {skill: _base_weight(skill, blueprint) for skill in allowed}

        if positioning == "cloud_platform_heavy":
            for skill in blueprint.priority_skills.get("P1", []):
                emphasis[skill] = 1.0
            for skill in blueprint.priority_skills.get("P2", []):
                emphasis[skill] = max(emphasis.get(skill, 0), 0.9)
            for skill in allowed:
                if skill.lower() in {"aws", "azure", "gcp", "terraform", "kubernetes"}:
                    emphasis[skill] = 1.0
        elif positioning == "databricks_platform_heavy":
            for skill in allowed:
                if skill.lower() in {"databricks", "apache spark", "spark", "delta lake", "unity catalog", "pyspark"}:
                    emphasis[skill] = max(emphasis.get(skill, 0), 0.95)
        elif positioning == "devops_automation_heavy":
            for skill in allowed:
                if skill.lower() in {"ci/cd", "terraform", "kubernetes", "docker", "helm", "python"}:
                    emphasis[skill] = max(emphasis.get(skill, 0), 0.95)
        elif positioning == "cloud_data_engineering_heavy":
            for skill in blueprint.priority_skills.get("P1", []) + blueprint.priority_skills.get("P2", []):
                emphasis[skill] = max(emphasis.get(skill, 0), 0.9)
            for skill in blueprint.priority_skills.get("P3", [])[:5]:
                emphasis[skill] = max(emphasis.get(skill, 0), 0.7)
        elif positioning == "ai_enabled_data_platform_heavy":
            for skill in allowed:
                lowered = skill.lower()
                if lowered in {"openai", "openai api", "claude", "claude api", "langchain", "rag", "databricks"}:
                    emphasis[skill] = max(emphasis.get(skill, 0), 0.95)

        variants.append(
            VariantStrategy(
                variant_id=variant_id,
                positioning=positioning,
                description=description,
                emphasis=emphasis,
                bullet_bias={
                    "P1": 1.0,
                    "P2": 0.85,
                    "P3": 0.55,
                    "P4": 0.25,
                },
                rules=[
                    "Use only P1, P2, P3, and approved P4 technologies.",
                    "Change emphasis, not the approved technology universe.",
                    "Do not introduce unrelated stacks or role identity drift.",
                ],
            )
        )

    return variants
