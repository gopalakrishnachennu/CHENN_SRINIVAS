"""Build executable repair plans from validation failures (Gate 1)."""

from __future__ import annotations

from typing import Any

from resume_engine.models.jd_blueprint import JDBlueprint
from resume_engine.models.validation_schema import ValidationBundle, ValidationIssue
from resume_engine.repair.patch_applier import CORE_SKILL_GROUP, RepairOperation


def _collect_issues(bundle: ValidationBundle) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for result in bundle.validator_results:
        issues.extend(result.issues)
    return issues


def _is_optional_p4_skill(skill: str, blueprint: JDBlueprint | None) -> bool:
    if not skill or blueprint is None:
        return False
    p4 = {item for item in blueprint.priority_skills.get("P4", [])}
    return skill in p4


def _candidate_verified_skills(candidate_profile: dict | None) -> set[str]:
    if not candidate_profile:
        return set()
    skills = set()
    for item in candidate_profile.get("technical_skills") or []:
        if isinstance(item, str) and item.strip():
            skills.add(item.strip().lower())
    for exp in candidate_profile.get("experience") or []:
        for fact in exp.get("truthful_facts") or []:
            if isinstance(fact, str):
                skills.add(fact.strip().lower())
    return skills


def _skill_supported_in_candidate(skill: str, candidate_profile: dict | None) -> bool:
    verified = _candidate_verified_skills(candidate_profile)
    needle = skill.strip().lower()
    if needle in verified:
        return True
    return any(needle in item or item in needle for item in verified)


def _choose_skill_group(resume_skills: dict[str, list[str]] | None) -> str:
    if resume_skills:
        if CORE_SKILL_GROUP in resume_skills:
            return CORE_SKILL_GROUP
        # Prefer first existing group for ATS stability.
        return next(iter(resume_skills.keys()))
    return CORE_SKILL_GROUP


def build_repair_plan(
    bundle: ValidationBundle,
    blueprint: JDBlueprint | None = None,
    *,
    generation_mode: str = "TEMPLATE",
    candidate_profile: dict | None = None,
    resume_technical_skills: dict[str, list[str]] | None = None,
) -> dict:
    issues = _collect_issues(bundle)
    failed_bullets = []
    missing_skills = []
    missing_responsibilities = []
    remove_technologies = []
    duplicate_locations = []
    targets = []
    operations: list[dict[str, Any]] = []
    unresolved_required_candidate_gaps: list[str] = []

    p4_skills = set(blueprint.priority_skills.get("P4", [])) if blueprint else set()
    allowed = set(blueprint.generation_contract.allowed_technologies) if blueprint else set()
    allowed_norm = {item.lower() for item in allowed}
    mode = (generation_mode or "TEMPLATE").upper()

    for issue in issues:
        if issue.location and "bullets" in issue.location:
            primary_location = issue.location.split(" / ")[0].strip()
            failed_bullets.append(primary_location)
            targets.append(
                {
                    "location": primary_location,
                    "reason_codes": [issue.code],
                }
            )
            # Prefer REPLACE for existing bullet locations.
            if "experience[" in primary_location and ".bullets[" in primary_location:
                try:
                    exp_part, bullet_part = primary_location.split(".bullets[")
                    exp_i = int(exp_part.split("[")[1].rstrip("]"))
                    bullet_i = int(bullet_part.rstrip("]"))
                    operations.append(
                        RepairOperation(
                            operation="REPLACE_EXPERIENCE_BULLET",
                            experience_index=exp_i,
                            bullet_index=bullet_i,
                            value="",  # LLM fills text
                            location=primary_location,
                        ).model_dump()
                    )
                except (ValueError, IndexError):
                    operations.append(
                        RepairOperation(
                            operation="REPLACE_TEXT",
                            location=primary_location,
                            value="",
                        ).model_dump()
                    )

        if issue.code in {"FAIL_P1_COVERAGE", "FAIL_P2_COVERAGE", "FAIL_P3_COVERAGE"}:
            for skill in issue.metadata.get("missing", []):
                if skill and skill not in p4_skills and not _is_optional_p4_skill(skill, blueprint):
                    missing_skills.append(skill)

        if issue.code == "FAIL_MISSING_REQUIRED_PLACEMENT":
            placement = issue.metadata.get("placement", "")
            skill = issue.metadata.get("skill", "")
            priority = issue.metadata.get("priority", "")
            if placement == "technical_skills_optional":
                continue
            if priority == "P4" or skill in p4_skills:
                continue
            if skill:
                missing_skills.append(skill)
                if placement and placement not in {"technical_skills", "professional_summary"}:
                    targets.append(
                        {
                            "location": placement,
                            "reason_codes": [issue.code],
                            "skill": skill,
                        }
                    )

        if issue.code == "FAIL_RESPONSIBILITY_COVERAGE":
            missing_responsibilities.append(issue.metadata.get("responsibility", ""))

        if issue.code in {"FAIL_AI_TOOL_MISSING_SKILLS", "FAIL_AI_TOOL_MISSING_RESPONSIBILITY"}:
            skill = issue.metadata.get("skill", "")
            if skill and skill not in p4_skills:
                missing_skills.append(skill)

        if issue.code in {"FAIL_PRIMARY_FAMILY_NOT_REPRESENTED", "FAIL_SECONDARY_FAMILY_NOT_RETAINED"}:
            missing_responsibilities.append(issue.message)

        if issue.code.startswith("FAIL_UNAPPROVED_TECHNOLOGY") or issue.code in {
            "FAIL_UNAPPROVED_BULLET_TECHNOLOGY",
            "FAIL_LLM_GENERATED_TECHNOLOGY",
            "FAIL_UNAPPROVED_TECHNOLOGY_IN_TEXT",
        }:
            tech = issue.metadata.get("technology") or issue.metadata.get("skill")
            if not tech:
                tech = issue.message.split(":")[-1].strip()
            if tech:
                remove_technologies.append(tech)
                operations.append(
                    RepairOperation(
                        operation="REMOVE_SKILL",
                        value=tech,
                        group=None,
                    ).model_dump()
                )

        if "DUPLICATE" in issue.code:
            duplicate_locations.append(issue.location)

        if issue.code == "FAIL_P4_OVERUSE":
            for skill in issue.metadata.get("p4_used", []):
                remove_technologies.append(skill)
                operations.append(
                    RepairOperation(
                        operation="REMOVE_SKILL",
                        value=skill,
                        group=None,
                    ).model_dump()
                )

    # Convert missing required skills into executable APPEND_SKILL ops.
    for skill in list(dict.fromkeys(item for item in missing_skills if item)):
        if skill.lower() not in allowed_norm and skill not in allowed:
            # Not blueprint-allowed — skip rather than invent.
            continue
        if mode == "CANDIDATE":
            if not _skill_supported_in_candidate(skill, candidate_profile):
                unresolved_required_candidate_gaps.append(skill)
                continue
        group = _choose_skill_group(resume_technical_skills)
        operations.append(
            RepairOperation(
                operation="APPEND_SKILL",
                group=group,
                value=skill,
            ).model_dump()
        )
        targets.append(
            {
                "location": f"technical_skills.{group}",
                "reason_codes": ["FAIL_MISSING_REQUIRED_SKILL"],
                "skill": skill,
                "operation": "APPEND_SKILL",
            }
        )

    # Deduplicate targets by location while merging reason codes.
    merged_targets: dict[str, dict] = {}
    for target in targets:
        location = target.get("location")
        if not location:
            continue
        if location not in merged_targets:
            merged_targets[location] = {
                "location": location,
                "reason_codes": list(target.get("reason_codes", [])),
            }
            if "skill" in target:
                merged_targets[location]["skill"] = target["skill"]
            if "operation" in target:
                merged_targets[location]["operation"] = target["operation"]
        else:
            for code in target.get("reason_codes", []):
                if code not in merged_targets[location]["reason_codes"]:
                    merged_targets[location]["reason_codes"].append(code)

    # Deduplicate operations.
    unique_ops: list[dict] = []
    seen_ops: set[tuple] = set()
    for op in operations:
        key = (
            op.get("operation"),
            op.get("group"),
            op.get("value"),
            op.get("location"),
            op.get("experience_index"),
            op.get("bullet_index"),
            op.get("project_index"),
        )
        if key in seen_ops:
            continue
        seen_ops.add(key)
        unique_ops.append(op)

    plan = {
        "required": bool(issues),
        "failed_bullets": list(dict.fromkeys(item for item in failed_bullets if item)),
        "missing_skills": list(dict.fromkeys(item for item in missing_skills if item)),
        "missing_responsibilities": list(
            dict.fromkeys(item for item in missing_responsibilities if item)
        ),
        "remove_technologies": list(dict.fromkeys(item for item in remove_technologies if item)),
        "duplicate_locations": list(dict.fromkeys(item for item in duplicate_locations if item)),
        "targets": list(merged_targets.values()),
        "operations": unique_ops,
        "issue_count": len(issues),
        "generation_mode": mode,
        "unresolved_required_candidate_gaps": list(
            dict.fromkeys(unresolved_required_candidate_gaps)
        ),
    }
    return plan
