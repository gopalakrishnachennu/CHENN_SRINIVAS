from resume_engine.models.jd_blueprint import JDBlueprint
from resume_engine.models.validation_schema import ValidationBundle, ValidationIssue


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


def build_repair_plan(
    bundle: ValidationBundle,
    blueprint: JDBlueprint | None = None,
) -> dict:
    issues = _collect_issues(bundle)
    failed_bullets = []
    missing_skills = []
    missing_responsibilities = []
    remove_technologies = []
    duplicate_locations = []
    targets = []

    p4_skills = set(blueprint.priority_skills.get("P4", [])) if blueprint else set()

    for issue in issues:
        if issue.location and "bullets" in issue.location:
            # Prefer the first location when validators join pairs with " / ".
            primary_location = issue.location.split(" / ")[0].strip()
            failed_bullets.append(primary_location)
            targets.append(
                {
                    "location": primary_location,
                    "reason_codes": [issue.code],
                }
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
                if placement:
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

        if issue.code.startswith("FAIL_UNAPPROVED_TECHNOLOGY"):
            remove_technologies.append(issue.message.split(":")[-1].strip())

        if "DUPLICATE" in issue.code:
            duplicate_locations.append(issue.location)

        if issue.code == "FAIL_P4_OVERUSE":
            # Overuse is fixed by removing optional skills, not stuffing more P4.
            for skill in issue.metadata.get("p4_used", []):
                remove_technologies.append(skill)

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
        else:
            for code in target.get("reason_codes", []):
                if code not in merged_targets[location]["reason_codes"]:
                    merged_targets[location]["reason_codes"].append(code)

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
        "issue_count": len(issues),
    }
    return plan
