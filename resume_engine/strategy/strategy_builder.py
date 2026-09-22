import json
from pathlib import Path

from resume_engine.config.settings import STRATEGY_STORAGE_DIR, ensure_storage_dirs
from resume_engine.models.jd_blueprint import JDBlueprint
from resume_engine.models.resume_strategy import ResumeStrategy
from resume_engine.strategy.role_positioning import build_positioning, forbidden_role_drift
from resume_engine.strategy.skill_placement import build_placement_requirements, group_skills_by_category


def _priority(blueprint: JDBlueprint, level: str) -> list[str]:
    return blueprint.priority_skills.get(level, [])


def build_strategy(blueprint: JDBlueprint) -> ResumeStrategy:
    p1 = _priority(blueprint, "P1")
    p2 = _priority(blueprint, "P2")
    p3 = _priority(blueprint, "P3")
    p4 = _priority(blueprint, "P4")

    summary_focus = list(dict.fromkeys(p1[:5] + p2[:3]))
    experience_focus = list(dict.fromkeys(p1 + p2 + p3[:4]))
    project_focus = list(dict.fromkeys(p2[:4] + p3[:4] + p4[:3]))

    strategy = ResumeStrategy(
        strategy_id=f"strategy_{blueprint.jd_hash}",
        jd_hash=blueprint.jd_hash,
        positioning=build_positioning(blueprint),
        summary_focus=summary_focus,
        experience_focus=experience_focus,
        project_focus=project_focus,
        technical_skill_categories=group_skills_by_category(blueprint),
        certification_treatment=blueprint.certifications,
        allowed_tools=blueprint.generation_contract.allowed_technologies,
        forbidden_drift=forbidden_role_drift(blueprint),
        bullet_allocation={
            "current": 5,
            "previous_1": 4,
            "previous_2": 3,
            "projects": 2,
        },
        placement_requirements=build_placement_requirements(blueprint),
        p4_limits={
            "max_optional_mentions_ratio": 0.35,
            "max_project_only_count": max(1, len(p4) // 2) if p4 else 0,
        },
    )
    return strategy


def save_strategy(strategy: ResumeStrategy) -> Path:
    ensure_storage_dirs()
    path = STRATEGY_STORAGE_DIR / f"{strategy.strategy_id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(strategy.model_dump(), f, indent=2, ensure_ascii=False)
    return path
