from resume_engine.models.jd_blueprint import JDBlueprint


def build_placement_requirements(blueprint: JDBlueprint) -> dict[str, list[str]]:
    requirements: dict[str, list[str]] = {}
    for entity in blueprint.entities:
        requirements[entity.name] = list(dict.fromkeys(entity.placement))
    return requirements


def group_skills_by_category(blueprint: JDBlueprint) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for entity in blueprint.entities:
        category = entity.category if entity.category != "adjacent" else "optional_adjacent"
        groups.setdefault(category, [])
        if entity.name not in groups[category]:
            groups[category].append(entity.name)
    return groups
