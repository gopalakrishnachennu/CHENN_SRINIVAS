import json
import os

from resume_engine.config.settings import DEFAULT_OPENAI_MODEL, PROMPT_VERSION
from resume_engine.generation.provenance import attach_skill_provenance
from resume_engine.llm.client import LLMClient
from resume_engine.models.jd_blueprint import JDBlueprint
from resume_engine.models.resume_schema import ResumeJSON
from resume_engine.models.resume_strategy import ResumeStrategy, VariantStrategy
from resume_engine.repair.patch_applier import (
    PatchApplicationError,
    RepairOperation,
    RepairPatchResponse,
    apply_resume_operations,
    apply_resume_patches,
)


def _deterministic_operations(repair_plan: dict) -> list[RepairOperation]:
    ops: list[RepairOperation] = []
    for item in repair_plan.get("operations", []):
        op = RepairOperation.model_validate(item)
        # Skill append/remove and valued ops are applied in Python without LLM.
        if op.operation in {"APPEND_SKILL", "REMOVE_SKILL", "REPLACE_SKILL"} and op.value:
            ops.append(op)
        elif op.operation in {
            "REPLACE_TEXT",
            "REPLACE_EXPERIENCE_BULLET",
            "REPLACE_PROJECT_BULLET",
            "APPEND_EXPERIENCE_BULLET",
        } and op.value:
            # Only apply if a concrete non-empty value is already provided.
            ops.append(op)
    return ops


def _needs_llm_text(repair_plan: dict) -> bool:
    for item in repair_plan.get("operations", []):
        op = RepairOperation.model_validate(item)
        if op.operation in {
            "REPLACE_TEXT",
            "REPLACE_EXPERIENCE_BULLET",
            "REPLACE_PROJECT_BULLET",
            "APPEND_EXPERIENCE_BULLET",
        } and not op.value:
            return True
    # Legacy failed bullets without typed ops still need LLM text.
    return bool(repair_plan.get("failed_bullets") and not repair_plan.get("operations"))


def rewrite_targeted_resume_parts(
    client: LLMClient | object,
    blueprint: JDBlueprint,
    strategy: ResumeStrategy,
    variant: VariantStrategy,
    resume: ResumeJSON,
    repair_plan: dict,
    model: str | None = None,
    run_id: str | None = None,
) -> ResumeJSON:
    """Apply deterministic Python operations; optionally request LLM text patches."""
    if not repair_plan.get("required"):
        return resume

    allowed = blueprint.generation_contract.allowed_technologies
    working = resume
    deterministic = _deterministic_operations(repair_plan)
    if deterministic:
        try:
            working, scope_issues = apply_resume_operations(
                working,
                deterministic,
                repair_plan=repair_plan,
                allowed_technologies=allowed,
            )
        except PatchApplicationError as exc:
            raise RuntimeError(f"{exc.code}: {exc.message}") from exc
        if scope_issues:
            codes = ", ".join(sorted({issue.code for issue in scope_issues}))
            raise RuntimeError(f"FAIL_REPAIR_SCOPE_VIOLATION: unrelated fields changed ({codes})")

    if not _needs_llm_text(repair_plan):
        working.variant_id = resume.variant_id
        working.source_blueprint_hash = resume.source_blueprint_hash
        return attach_skill_provenance(blueprint, working)

    system = """
You are a targeted resume repair engine.

Return ONLY a RepairPatchResponse JSON object.
Prefer typed operations when possible. Legacy patches are also accepted.

Supported operations:
- REPLACE_TEXT (location, value)
- REPLACE_EXPERIENCE_BULLET (experience_index, bullet_index, value)
- APPEND_EXPERIENCE_BULLET (experience_index, value)
- REPLACE_PROJECT_BULLET (project_index, bullet_index, value)

Do NOT invent technologies, employers, certifications, or candidate facts.
Do NOT add skills — Python already applies APPEND_SKILL / REMOVE_SKILL.
Only supply replacement text for failing bullets/summary listed in the repair plan.
"""
    payload = {
        "jd_blueprint": blueprint.as_prompt_payload(),
        "resume_strategy": strategy.model_dump(),
        "variant_strategy": variant.model_dump(),
        "current_resume": working.model_dump(),
        "repair_plan": repair_plan,
        "allowed_technologies": allowed,
        "output_schema": {
            "operations": [
                {
                    "operation": "REPLACE_EXPERIENCE_BULLET",
                    "experience_index": 0,
                    "bullet_index": 0,
                    "value": "replacement text",
                }
            ],
            "patches": [
                {
                    "location": "experience[0].bullets[0]",
                    "replacement": "replacement text",
                }
            ],
        },
    }

    resolved_model = model or os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload, indent=2, ensure_ascii=False)},
    ]
    if isinstance(client, LLMClient):
        response = client.parse(
            model=resolved_model,
            input=messages,
            text_format=RepairPatchResponse,
            run_id=run_id,
            prompt_version=PROMPT_VERSION,
            operation="targeted_repair",
        )
    else:
        response = client.responses.parse(
            model=resolved_model,
            input=messages,
            text_format=RepairPatchResponse,
        )

    if response.output_parsed is None:
        raise RuntimeError("Targeted repair returned no structured RepairPatchResponse.")

    patch_response: RepairPatchResponse = response.output_parsed
    try:
        repaired, scope_issues = apply_resume_patches(
            resume=working,
            patches=patch_response.patches,
            operations=patch_response.operations,
            repair_plan=repair_plan,
            allowed_technologies=allowed,
        )
    except PatchApplicationError as exc:
        raise RuntimeError(f"{exc.code}: {exc.message}") from exc

    if scope_issues:
        codes = ", ".join(sorted({issue.code for issue in scope_issues}))
        raise RuntimeError(f"FAIL_REPAIR_SCOPE_VIOLATION: unrelated fields changed ({codes})")

    repaired.variant_id = resume.variant_id
    repaired.source_blueprint_hash = resume.source_blueprint_hash
    repaired = attach_skill_provenance(blueprint, repaired)
    return repaired
