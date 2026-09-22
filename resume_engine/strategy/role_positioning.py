from resume_engine.models.jd_blueprint import JDBlueprint


def build_positioning(blueprint: JDBlueprint) -> dict[str, str]:
    return {
        "target_role": blueprint.job.target_title or "Target Role",
        "primary_family": blueprint.job.primary_family,
        "secondary_family": blueprint.job.secondary_family,
        "seniority": blueprint.job.seniority,
        "hybrid_positioning": (
            "hybrid"
            if blueprint.job.secondary_family != "none" and blueprint.job.hybrid_probability >= 0.55
            else "primary_family_focused"
        ),
    }


def forbidden_role_drift(blueprint: JDBlueprint) -> list[str]:
    primary = blueprint.job.primary_family
    drift_map = {
        "devops_cloud": ["data_scientist", "frontend_only", "salesforce_admin"],
        "data_engineering": ["data_scientist", "frontend_only", "network_support_only"],
        "ai_ml": ["frontend_only", "manual_qa_only", "desktop_support_only"],
        "data_analytics": ["devops_only", "data_scientist_only", "frontend_only"],
        "software_engineering": ["data_scientist_only", "desktop_support_only"],
        "infrastructure_support": ["data_scientist", "marketing_analytics_only"],
        "test_engineering": ["data_scientist", "devops_architect_only"],
    }
    return drift_map.get(primary, ["unrelated_role_identity"])
