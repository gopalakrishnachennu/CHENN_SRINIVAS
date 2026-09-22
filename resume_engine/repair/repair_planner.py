from resume_engine.models.validation_schema import ValidationBundle, ValidationIssue


def _collect_issues(bundle: ValidationBundle) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for result in bundle.validator_results:
        issues.extend(result.issues)
    return issues


def build_repair_plan(bundle: ValidationBundle) -> dict:
    issues = _collect_issues(bundle)
    failed_bullets = []
    missing_skills = []
    missing_responsibilities = []
    remove_technologies = []
    duplicate_locations = []

    for issue in issues:
        if issue.location and "bullets" in issue.location:
            failed_bullets.append(issue.location)
        if issue.code in {"FAIL_P1_COVERAGE", "FAIL_P2_COVERAGE", "FAIL_P3_COVERAGE"}:
            missing_skills.extend(issue.metadata.get("missing", []))
        if issue.code == "FAIL_MISSING_REQUIRED_PLACEMENT":
            missing_skills.append(issue.metadata.get("skill", ""))
        if issue.code == "FAIL_RESPONSIBILITY_COVERAGE":
            missing_responsibilities.append(issue.metadata.get("responsibility", ""))
        if issue.code in {"FAIL_AI_TOOL_MISSING_SKILLS", "FAIL_AI_TOOL_MISSING_RESPONSIBILITY"}:
            missing_skills.append(issue.metadata.get("skill", ""))
        if issue.code in {"FAIL_PRIMARY_FAMILY_NOT_REPRESENTED", "FAIL_SECONDARY_FAMILY_NOT_RETAINED"}:
            missing_responsibilities.append(issue.message)
        if issue.code.startswith("FAIL_UNAPPROVED_TECHNOLOGY"):
            remove_technologies.append(issue.message.split(":")[-1].strip())
        if "DUPLICATE" in issue.code:
            duplicate_locations.append(issue.location)

    plan = {
        "required": bool(issues),
        "failed_bullets": list(dict.fromkeys(item for item in failed_bullets if item)),
        "missing_skills": list(dict.fromkeys(item for item in missing_skills if item)),
        "missing_responsibilities": list(dict.fromkeys(item for item in missing_responsibilities if item)),
        "remove_technologies": list(dict.fromkeys(item for item in remove_technologies if item)),
        "duplicate_locations": list(dict.fromkeys(item for item in duplicate_locations if item)),
        "issue_count": len(issues),
    }
    return plan
