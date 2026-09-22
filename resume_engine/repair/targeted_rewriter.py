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
    RepairPatchResponse,
    apply_resume_patches,
)


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
    """Request ONLY patches from the model and apply them in Python."""
    if not repair_plan.get("required"):
        return resume

    system = """
You are a targeted resume repair engine.

Return ONLY a RepairPatchResponse JSON object with a patches list.
Each patch must include:
- location: an exact resume path from repair_plan.targets / failed_bullets
  (example: experience[0].bullets[3] or summary)
- replacement: the full replacement string for that location only

STRICT RULES:
1. Do NOT return a full resume.
2. Do NOT invent locations that are not in the repair plan targets.
3. Do NOT modify unrelated sections.
4. Do not add technologies outside allowed_technologies.
5. Do not invent candidate history, employers, certifications, metrics, or tools.
6. Prefer the fewest patches needed to address the listed failures.
"""
    payload = {
        "jd_blueprint": blueprint.as_prompt_payload(),
        "resume_strategy": strategy.model_dump(),
        "variant_strategy": variant.model_dump(),
        "current_resume": resume.model_dump(),
        "repair_plan": repair_plan,
        "allowed_technologies": blueprint.generation_contract.allowed_technologies,
        "output_schema": {
            "patches": [
                {
                    "location": "experience[0].bullets[0]",
                    "replacement": "replacement text",
                }
            ]
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
            resume=resume,
            patches=patch_response.patches,
            repair_plan=repair_plan,
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
