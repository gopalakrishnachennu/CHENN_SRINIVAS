"""Deterministic patch application and repair-scope mutation guards."""

from __future__ import annotations

import copy
import re
from typing import Any

from pydantic import BaseModel, Field

from resume_engine.models.resume_schema import ResumeJSON
from resume_engine.models.validation_schema import ValidationIssue


LOCATION_RE = re.compile(
    r"^(?:"
    r"summary|"
    r"target_title|"
    r"experience\[(?P<exp_i>\d+)\]\.(?:bullets\[(?P<exp_b>\d+)\]|title|company)|"
    r"projects\[(?P<proj_i>\d+)\]\.(?:bullets\[(?P<proj_b>\d+)\]|summary|name)|"
    r"technical_skills\.(?P<skill_group>[^.\[\]]+)(?:\[(?P<skill_i>\d+)\])?"
    r")$"
)


class ResumePatch(BaseModel):
    location: str
    replacement: str


class RepairPatchResponse(BaseModel):
    patches: list[ResumePatch] = Field(default_factory=list)


class PatchApplicationError(Exception):
    def __init__(self, code: str, message: str, location: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.location = location


def parse_location(location: str) -> re.Match[str]:
    match = LOCATION_RE.match(location.strip())
    if match is None:
        raise PatchApplicationError(
            "FAIL_INVALID_PATCH_LOCATION",
            f"Malformed or unsupported patch location: {location}",
            location,
        )
    return match


def get_value_at_location(resume: ResumeJSON, location: str) -> Any:
    match = parse_location(location)
    data = resume.model_dump()

    if location == "summary":
        return data["summary"]
    if location == "target_title":
        return data["target_title"]

    if match.group("exp_i") is not None:
        exp_i = int(match.group("exp_i"))
        if exp_i < 0 or exp_i >= len(data["experience"]):
            raise PatchApplicationError(
                "FAIL_INVALID_PATCH_LOCATION",
                f"Experience index out of range: {location}",
                location,
            )
        exp = data["experience"][exp_i]
        if match.group("exp_b") is not None:
            bullet_i = int(match.group("exp_b"))
            if bullet_i < 0 or bullet_i >= len(exp["bullets"]):
                raise PatchApplicationError(
                    "FAIL_INVALID_PATCH_LOCATION",
                    f"Bullet index out of range: {location}",
                    location,
                )
            return exp["bullets"][bullet_i]
        if location.endswith(".title"):
            return exp["title"]
        if location.endswith(".company"):
            return exp["company"]

    if match.group("proj_i") is not None:
        proj_i = int(match.group("proj_i"))
        if proj_i < 0 or proj_i >= len(data["projects"]):
            raise PatchApplicationError(
                "FAIL_INVALID_PATCH_LOCATION",
                f"Project index out of range: {location}",
                location,
            )
        project = data["projects"][proj_i]
        if match.group("proj_b") is not None:
            bullet_i = int(match.group("proj_b"))
            if bullet_i < 0 or bullet_i >= len(project["bullets"]):
                raise PatchApplicationError(
                    "FAIL_INVALID_PATCH_LOCATION",
                    f"Project bullet index out of range: {location}",
                    location,
                )
            return project["bullets"][bullet_i]
        if location.endswith(".summary"):
            return project["summary"]
        if location.endswith(".name"):
            return project["name"]

    if match.group("skill_group") is not None:
        group = match.group("skill_group")
        if group not in data["technical_skills"]:
            raise PatchApplicationError(
                "FAIL_INVALID_PATCH_LOCATION",
                f"Unknown technical skill group: {group}",
                location,
            )
        skills = data["technical_skills"][group]
        if match.group("skill_i") is not None:
            skill_i = int(match.group("skill_i"))
            if skill_i < 0 or skill_i >= len(skills):
                raise PatchApplicationError(
                    "FAIL_INVALID_PATCH_LOCATION",
                    f"Skill index out of range: {location}",
                    location,
                )
            return skills[skill_i]
        return skills

    raise PatchApplicationError(
        "FAIL_INVALID_PATCH_LOCATION",
        f"Unable to resolve patch location: {location}",
        location,
    )


def set_value_at_location(resume: ResumeJSON, location: str, replacement: str) -> None:
    match = parse_location(location)

    if location == "summary":
        resume.summary = replacement
        return
    if location == "target_title":
        resume.target_title = replacement
        return

    if match.group("exp_i") is not None:
        exp_i = int(match.group("exp_i"))
        if exp_i < 0 or exp_i >= len(resume.experience):
            raise PatchApplicationError(
                "FAIL_INVALID_PATCH_LOCATION",
                f"Experience index out of range: {location}",
                location,
            )
        exp = resume.experience[exp_i]
        if match.group("exp_b") is not None:
            bullet_i = int(match.group("exp_b"))
            if bullet_i < 0 or bullet_i >= len(exp.bullets):
                raise PatchApplicationError(
                    "FAIL_INVALID_PATCH_LOCATION",
                    f"Bullet index out of range: {location}",
                    location,
                )
            exp.bullets[bullet_i] = replacement
            return
        if location.endswith(".title"):
            exp.title = replacement
            return
        if location.endswith(".company"):
            exp.company = replacement
            return

    if match.group("proj_i") is not None:
        proj_i = int(match.group("proj_i"))
        if proj_i < 0 or proj_i >= len(resume.projects):
            raise PatchApplicationError(
                "FAIL_INVALID_PATCH_LOCATION",
                f"Project index out of range: {location}",
                location,
            )
        project = resume.projects[proj_i]
        if match.group("proj_b") is not None:
            bullet_i = int(match.group("proj_b"))
            if bullet_i < 0 or bullet_i >= len(project.bullets):
                raise PatchApplicationError(
                    "FAIL_INVALID_PATCH_LOCATION",
                    f"Project bullet index out of range: {location}",
                    location,
                )
            project.bullets[bullet_i] = replacement
            return
        if location.endswith(".summary"):
            project.summary = replacement
            return
        if location.endswith(".name"):
            project.name = replacement
            return

    if match.group("skill_group") is not None:
        group = match.group("skill_group")
        if group not in resume.technical_skills:
            raise PatchApplicationError(
                "FAIL_INVALID_PATCH_LOCATION",
                f"Unknown technical skill group: {group}",
                location,
            )
        if match.group("skill_i") is not None:
            skill_i = int(match.group("skill_i"))
            skills = resume.technical_skills[group]
            if skill_i < 0 or skill_i >= len(skills):
                raise PatchApplicationError(
                    "FAIL_INVALID_PATCH_LOCATION",
                    f"Skill index out of range: {location}",
                    location,
                )
            skills[skill_i] = replacement
            return
        # Whole-group replacement is not supported for string patches.
        raise PatchApplicationError(
            "FAIL_INVALID_PATCH_LOCATION",
            f"Skill group patches must target an indexed skill: {location}",
            location,
        )

    raise PatchApplicationError(
        "FAIL_INVALID_PATCH_LOCATION",
        f"Unable to apply patch location: {location}",
        location,
    )


def snapshot_non_target_fields(resume: ResumeJSON, target_locations: set[str]) -> dict[str, Any]:
    """Capture values for every mutable leaf not listed in target_locations."""
    snapshot: dict[str, Any] = {}
    data = resume.model_dump()

    snapshot["summary"] = data["summary"]
    snapshot["target_title"] = data["target_title"]
    snapshot["certifications"] = copy.deepcopy(data["certifications"])
    snapshot["technical_skills"] = copy.deepcopy(data["technical_skills"])

    for exp_i, exp in enumerate(data["experience"]):
        snapshot[f"experience[{exp_i}].company"] = exp["company"]
        snapshot[f"experience[{exp_i}].title"] = exp["title"]
        for bullet_i, bullet in enumerate(exp["bullets"]):
            snapshot[f"experience[{exp_i}].bullets[{bullet_i}]"] = bullet

    for proj_i, project in enumerate(data["projects"]):
        snapshot[f"projects[{proj_i}].name"] = project["name"]
        snapshot[f"projects[{proj_i}].summary"] = project["summary"]
        snapshot[f"projects[{proj_i}].technologies"] = copy.deepcopy(project["technologies"])
        for bullet_i, bullet in enumerate(project["bullets"]):
            snapshot[f"projects[{proj_i}].bullets[{bullet_i}]"] = bullet

    for location in target_locations:
        snapshot.pop(location, None)
        # If a skill leaf is targeted, keep the group container but allow leaf change.
        if location.startswith("technical_skills."):
            # Drop indexed skill from deep compare by rebuilding after apply.
            pass

    # Always protect certifications / non-targeted skill groups via deep compare below.
    return snapshot


def allowed_locations_from_plan(repair_plan: dict) -> set[str]:
    allowed: set[str] = set()
    for target in repair_plan.get("targets", []):
        location = target.get("location")
        if location:
            allowed.add(location)
    for location in repair_plan.get("failed_bullets", []):
        if location:
            allowed.add(location.split(" / ")[0].strip())
    # Summary / skills may be repaired when explicitly listed as placement targets.
    for location in repair_plan.get("duplicate_locations", []):
        if location:
            allowed.add(location.split(" / ")[0].strip())
    return allowed


def apply_resume_patches(
    resume: ResumeJSON,
    patches: list[ResumePatch],
    repair_plan: dict | None = None,
) -> tuple[ResumeJSON, list[ValidationIssue]]:
    """
    Apply patches deterministically onto a deepcopy of resume.

    Returns (patched_resume, scope_issues).
    Raises PatchApplicationError for invalid/out-of-scope locations.
    """
    allowed = allowed_locations_from_plan(repair_plan or {})
    if repair_plan is not None:
        for patch in patches:
            if patch.location not in allowed:
                raise PatchApplicationError(
                    "FAIL_OUT_OF_SCOPE_PATCH",
                    f"Patch location not present in repair plan targets: {patch.location}",
                    patch.location,
                )

    target_locations = {patch.location for patch in patches}
    before_snapshot = snapshot_non_target_fields(resume, target_locations)
    patched = resume.model_copy(deep=True)

    for patch in patches:
        # Validate location exists on original before mutation.
        get_value_at_location(patched, patch.location)
        set_value_at_location(patched, patch.location, patch.replacement)

    after_snapshot = snapshot_non_target_fields(patched, target_locations)
    issues: list[ValidationIssue] = []

    # Compare protected non-target leaf values.
    for key, before_value in before_snapshot.items():
        if key in {"technical_skills", "certifications"}:
            continue
        after_value = after_snapshot.get(key)
        if before_value != after_value:
            issues.append(
                ValidationIssue(
                    code="FAIL_REPAIR_SCOPE_VIOLATION",
                    severity="error",
                    message=f"Non-target field changed during repair: {key}",
                    location=key,
                    repair_hint="Re-run patch repair without modifying unrelated fields.",
                )
            )

    if before_snapshot.get("certifications") != after_snapshot.get("certifications"):
        issues.append(
            ValidationIssue(
                code="FAIL_REPAIR_SCOPE_VIOLATION",
                severity="error",
                message="Certifications changed during repair without being targeted.",
                location="certifications",
            )
        )

    # Technical skills: allow only explicitly patched indexed leaves to change.
    before_skills = before_snapshot.get("technical_skills", {})
    after_skills = after_snapshot.get("technical_skills", {})
    if before_skills != after_skills:
        for group, skills in before_skills.items():
            after_group = after_skills.get(group, [])
            if group not in after_skills:
                issues.append(
                    ValidationIssue(
                        code="FAIL_REPAIR_SCOPE_VIOLATION",
                        severity="error",
                        message=f"Skill group removed during repair: {group}",
                        location=f"technical_skills.{group}",
                    )
                )
                continue
            if len(skills) != len(after_group):
                # Length change only OK if a specific index was targeted — still flag group reshape.
                issues.append(
                    ValidationIssue(
                        code="FAIL_REPAIR_SCOPE_VIOLATION",
                        severity="error",
                        message=f"Skill group length changed during repair: {group}",
                        location=f"technical_skills.{group}",
                    )
                )
                continue
            for idx, skill in enumerate(skills):
                leaf = f"technical_skills.{group}[{idx}]"
                if leaf in target_locations:
                    continue
                if after_group[idx] != skill:
                    issues.append(
                        ValidationIssue(
                            code="FAIL_REPAIR_SCOPE_VIOLATION",
                            severity="error",
                            message=f"Non-target skill changed during repair: {leaf}",
                            location=leaf,
                        )
                    )
        for group in after_skills:
            if group not in before_skills:
                issues.append(
                    ValidationIssue(
                        code="FAIL_REPAIR_SCOPE_VIOLATION",
                        severity="error",
                        message=f"Skill group added during repair: {group}",
                        location=f"technical_skills.{group}",
                    )
                )

    return patched, issues
