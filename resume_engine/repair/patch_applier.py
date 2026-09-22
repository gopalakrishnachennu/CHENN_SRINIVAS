"""Deterministic patch / repair-operation application and scope guards (Gate 1)."""

from __future__ import annotations

import copy
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from resume_engine.models.resume_schema import ResumeJSON
from resume_engine.models.validation_schema import ValidationIssue

CORE_SKILL_GROUP = "Core Technologies"

LOCATION_RE = re.compile(
    r"^(?:"
    r"summary|"
    r"target_title|"
    r"experience\[(?P<exp_i>\d+)\]\.(?:bullets\[(?P<exp_b>\d+)\]|title|company)|"
    r"projects\[(?P<proj_i>\d+)\]\.(?:bullets\[(?P<proj_b>\d+)\]|summary|name)|"
    r"technical_skills\.(?P<skill_group>[^.\[\]]+)(?:\[(?P<skill_i>\d+)\])?"
    r")$"
)

RepairOpName = Literal[
    "REPLACE_TEXT",
    "REPLACE_SKILL",
    "APPEND_SKILL",
    "REMOVE_SKILL",
    "REPLACE_EXPERIENCE_BULLET",
    "APPEND_EXPERIENCE_BULLET",
    "REPLACE_PROJECT_BULLET",
]


class ResumePatch(BaseModel):
    """Legacy patch form — internally treated as REPLACE_TEXT."""

    location: str
    replacement: str


class RepairOperation(BaseModel):
    operation: RepairOpName
    location: str | None = None
    value: str | None = None
    group: str | None = None
    experience_index: int | None = None
    project_index: int | None = None
    bullet_index: int | None = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_legacy(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if "operation" not in data and "location" in data and "replacement" in data:
            return {
                "operation": "REPLACE_TEXT",
                "location": data.get("location"),
                "value": data.get("replacement"),
            }
        if data.get("value") is None and data.get("replacement") is not None:
            data = {**data, "value": data.get("replacement")}
        return data


class RepairPatchResponse(BaseModel):
    """LLM may return legacy patches and/or typed operations."""

    patches: list[ResumePatch] = Field(default_factory=list)
    operations: list[RepairOperation] = Field(default_factory=list)

    def normalized_operations(self) -> list[RepairOperation]:
        ops = list(self.operations)
        for patch in self.patches:
            ops.append(
                RepairOperation(
                    operation="REPLACE_TEXT",
                    location=patch.location,
                    value=patch.replacement,
                )
            )
        return ops


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


def _normalize_skill(value: str) -> str:
    return value.strip().lower()


def _assert_technology_allowed(value: str, allowed: set[str] | None) -> None:
    if allowed is None:
        return
    if not value:
        raise PatchApplicationError(
            "FAIL_REPAIR_UNAPPROVED_TECHNOLOGY",
            "Empty technology value is not allowed in repair.",
        )
    allowed_norm = {_normalize_skill(item) for item in allowed}
    if _normalize_skill(value) not in allowed_norm:
        # Also allow exact case-insensitive containment in allowed list names.
        if not any(_normalize_skill(value) == _normalize_skill(item) for item in allowed):
            raise PatchApplicationError(
                "FAIL_REPAIR_UNAPPROVED_TECHNOLOGY",
                f"Repair attempted to introduce unapproved technology: {value}",
            )


def apply_repair_operation(
    resume: ResumeJSON,
    operation: RepairOperation,
    *,
    allowed_technologies: list[str] | None = None,
) -> None:
    allowed = set(allowed_technologies) if allowed_technologies is not None else None
    op = operation.operation
    value = operation.value or ""

    if op == "REPLACE_TEXT":
        if not operation.location:
            raise PatchApplicationError("FAIL_INVALID_PATCH_LOCATION", "REPLACE_TEXT requires location")
        get_value_at_location(resume, operation.location)
        set_value_at_location(resume, operation.location, value)
        return

    if op == "REPLACE_SKILL":
        group = operation.group
        if not group or group not in resume.technical_skills:
            raise PatchApplicationError(
                "FAIL_INVALID_PATCH_LOCATION",
                f"REPLACE_SKILL unknown group: {group}",
            )
        if operation.bullet_index is None:
            raise PatchApplicationError("FAIL_INVALID_PATCH_LOCATION", "REPLACE_SKILL requires bullet_index")
        _assert_technology_allowed(value, allowed)
        skills = resume.technical_skills[group]
        idx = operation.bullet_index
        if idx < 0 or idx >= len(skills):
            raise PatchApplicationError("FAIL_INVALID_PATCH_LOCATION", f"Skill index out of range: {idx}")
        skills[idx] = value
        return

    if op == "APPEND_SKILL":
        _assert_technology_allowed(value, allowed)
        group = operation.group or CORE_SKILL_GROUP
        if group not in resume.technical_skills:
            resume.technical_skills[group] = []
        existing = {_normalize_skill(item) for item in resume.technical_skills[group]}
        if _normalize_skill(value) not in existing:
            resume.technical_skills[group].append(value)
        return

    if op == "REMOVE_SKILL":
        group = operation.group
        if not group:
            # Search all groups for the value.
            for g, skills in list(resume.technical_skills.items()):
                resume.technical_skills[g] = [
                    skill for skill in skills if _normalize_skill(skill) != _normalize_skill(value)
                ]
            return
        if group not in resume.technical_skills:
            return
        resume.technical_skills[group] = [
            skill
            for skill in resume.technical_skills[group]
            if _normalize_skill(skill) != _normalize_skill(value)
        ]
        return

    if op == "REPLACE_EXPERIENCE_BULLET":
        exp_i = operation.experience_index
        bullet_i = operation.bullet_index
        if exp_i is None or bullet_i is None:
            raise PatchApplicationError(
                "FAIL_INVALID_PATCH_LOCATION",
                "REPLACE_EXPERIENCE_BULLET requires experience_index and bullet_index",
            )
        location = f"experience[{exp_i}].bullets[{bullet_i}]"
        get_value_at_location(resume, location)
        set_value_at_location(resume, location, value)
        return

    if op == "APPEND_EXPERIENCE_BULLET":
        exp_i = operation.experience_index
        if exp_i is None or exp_i < 0 or exp_i >= len(resume.experience):
            raise PatchApplicationError(
                "FAIL_INVALID_PATCH_LOCATION",
                f"APPEND_EXPERIENCE_BULLET invalid experience_index: {exp_i}",
            )
        resume.experience[exp_i].bullets.append(value)
        return

    if op == "REPLACE_PROJECT_BULLET":
        proj_i = operation.project_index
        bullet_i = operation.bullet_index
        if proj_i is None or bullet_i is None:
            raise PatchApplicationError(
                "FAIL_INVALID_PATCH_LOCATION",
                "REPLACE_PROJECT_BULLET requires project_index and bullet_index",
            )
        location = f"projects[{proj_i}].bullets[{bullet_i}]"
        get_value_at_location(resume, location)
        set_value_at_location(resume, location, value)
        return

    raise PatchApplicationError("FAIL_INVALID_PATCH_LOCATION", f"Unsupported operation: {op}")


def snapshot_non_target_fields(resume: ResumeJSON, target_locations: set[str]) -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    data = resume.model_dump()

    snapshot["summary"] = data["summary"]
    snapshot["target_title"] = data["target_title"]
    snapshot["certifications"] = copy.deepcopy(data["certifications"])
    snapshot["technical_skills"] = copy.deepcopy(data["technical_skills"])
    snapshot["experience_len"] = len(data["experience"])
    snapshot["project_len"] = len(data["projects"])

    for exp_i, exp in enumerate(data["experience"]):
        snapshot[f"experience[{exp_i}].company"] = exp["company"]
        snapshot[f"experience[{exp_i}].title"] = exp["title"]
        snapshot[f"experience[{exp_i}].bullets_len"] = len(exp["bullets"])
        for bullet_i, bullet in enumerate(exp["bullets"]):
            snapshot[f"experience[{exp_i}].bullets[{bullet_i}]"] = bullet

    for proj_i, project in enumerate(data["projects"]):
        snapshot[f"projects[{proj_i}].name"] = project["name"]
        snapshot[f"projects[{proj_i}].summary"] = project["summary"]
        snapshot[f"projects[{proj_i}].technologies"] = copy.deepcopy(project["technologies"])
        snapshot[f"projects[{proj_i}].bullets_len"] = len(project["bullets"])
        for bullet_i, bullet in enumerate(project["bullets"]):
            snapshot[f"projects[{proj_i}].bullets[{bullet_i}]"] = bullet

    for location in target_locations:
        snapshot.pop(location, None)

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
    for location in repair_plan.get("duplicate_locations", []):
        if location:
            allowed.add(location.split(" / ")[0].strip())
    for op in repair_plan.get("operations", []):
        if isinstance(op, dict) and op.get("location"):
            allowed.add(op["location"])
    return allowed


def _operation_target_keys(operation: RepairOperation) -> set[str]:
    keys: set[str] = set()
    if operation.operation == "REPLACE_TEXT" and operation.location:
        keys.add(operation.location)
    if operation.operation in {"APPEND_SKILL", "REMOVE_SKILL", "REPLACE_SKILL"}:
        keys.add(f"skill_op:{operation.operation}:{operation.group}:{operation.value}")
        keys.add("technical_skills")
    if operation.operation == "REPLACE_EXPERIENCE_BULLET":
        keys.add(f"experience[{operation.experience_index}].bullets[{operation.bullet_index}]")
    if operation.operation == "APPEND_EXPERIENCE_BULLET":
        keys.add(f"experience[{operation.experience_index}].bullets_append")
        keys.add(f"experience[{operation.experience_index}].bullets_len")
    if operation.operation == "REPLACE_PROJECT_BULLET":
        keys.add(f"projects[{operation.project_index}].bullets[{operation.bullet_index}]")
    return keys


def apply_resume_operations(
    resume: ResumeJSON,
    operations: list[RepairOperation],
    repair_plan: dict | None = None,
    *,
    allowed_technologies: list[str] | None = None,
) -> tuple[ResumeJSON, list[ValidationIssue]]:
    plan_ops = []
    if repair_plan:
        for item in repair_plan.get("operations", []):
            if isinstance(item, dict):
                plan_ops.append(RepairOperation.model_validate(item))
            elif isinstance(item, RepairOperation):
                plan_ops.append(item)

    # Deterministic plan operations always allowed; LLM ops must match plan or legacy locations.
    plan_op_keys = {(_op.operation, _op.group, _op.value, _op.location, _op.experience_index, _op.bullet_index, _op.project_index) for _op in plan_ops}
    legacy_allowed = allowed_locations_from_plan(repair_plan or {})

    target_keys: set[str] = set()
    for operation in operations:
        target_keys |= _operation_target_keys(operation)

    before_snapshot = snapshot_non_target_fields(resume, set())
    patched = resume.model_copy(deep=True)

    for operation in operations:
        key = (
            operation.operation,
            operation.group,
            operation.value,
            operation.location,
            operation.experience_index,
            operation.bullet_index,
            operation.project_index,
        )
        if repair_plan is not None:
            if key not in plan_op_keys:
                if operation.operation == "REPLACE_TEXT" and operation.location in legacy_allowed:
                    pass
                elif plan_ops or legacy_allowed:
                    # Allow exact planned skill ops already converted.
                    if not any(
                        op.operation == operation.operation
                        and (op.value or "") == (operation.value or "")
                        and (op.group or None) == (operation.group or None)
                        for op in plan_ops
                    ):
                        raise PatchApplicationError(
                            "FAIL_OUT_OF_SCOPE_PATCH",
                            f"Repair operation not present in repair plan: {operation.operation}",
                            operation.location,
                        )
        apply_repair_operation(
            patched,
            operation,
            allowed_technologies=allowed_technologies,
        )

    after_snapshot = snapshot_non_target_fields(patched, set())
    issues: list[ValidationIssue] = []

    # Protect certifications always.
    if before_snapshot.get("certifications") != after_snapshot.get("certifications"):
        issues.append(
            ValidationIssue(
                code="FAIL_REPAIR_SCOPE_VIOLATION",
                severity="error",
                message="Certifications changed during repair without being targeted.",
                location="certifications",
            )
        )

    # Protect non-targeted experience/project leaf text.
    for key, before_value in before_snapshot.items():
        if key in {"technical_skills", "certifications", "experience_len", "project_len"}:
            continue
        if key.endswith(".bullets_len"):
            # Length may change only for APPEND_* on that experience/project.
            continue
        if key in target_keys:
            continue
        # Skill ops may change technical_skills container; handled below.
        if key.startswith("experience[") or key.startswith("projects[") or key in {"summary", "target_title"}:
            if before_value != after_snapshot.get(key):
                # Allow append: old bullets unchanged, new index only.
                if ".bullets[" in key:
                    # If this bullet index existed before and wasn't targeted, must match.
                    issues.append(
                        ValidationIssue(
                            code="FAIL_REPAIR_SCOPE_VIOLATION",
                            severity="error",
                            message=f"Non-target field changed during repair: {key}",
                            location=key,
                        )
                    )
                elif key in {"summary", "target_title"} and key not in target_keys:
                    issues.append(
                        ValidationIssue(
                            code="FAIL_REPAIR_SCOPE_VIOLATION",
                            severity="error",
                            message=f"Non-target field changed during repair: {key}",
                            location=key,
                        )
                    )
                elif key.endswith(".company") or key.endswith(".title") or key.endswith(".name") or key.endswith(".summary"):
                    if not key.endswith(".bullets_len"):
                        issues.append(
                            ValidationIssue(
                                code="FAIL_REPAIR_SCOPE_VIOLATION",
                                severity="error",
                                message=f"Non-target field changed during repair: {key}",
                                location=key,
                            )
                        )

    return patched, issues


def apply_resume_patches(
    resume: ResumeJSON,
    patches: list[ResumePatch],
    repair_plan: dict | None = None,
    *,
    allowed_technologies: list[str] | None = None,
    operations: list[RepairOperation] | None = None,
) -> tuple[ResumeJSON, list[ValidationIssue]]:
    """
    Apply legacy patches and/or typed operations onto a deepcopy of resume.
    """
    ops: list[RepairOperation] = list(operations or [])
    for patch in patches:
        ops.append(
            RepairOperation(
                operation="REPLACE_TEXT",
                location=patch.location,
                value=patch.replacement,
            )
        )
    # Prefer plan operations when caller only passes legacy empty patches.
    if not ops and repair_plan:
        for item in repair_plan.get("operations", []):
            ops.append(RepairOperation.model_validate(item))
    return apply_resume_operations(
        resume,
        ops,
        repair_plan=repair_plan,
        allowed_technologies=allowed_technologies,
    )
