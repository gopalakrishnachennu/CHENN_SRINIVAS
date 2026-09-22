import json
import os

from openai import OpenAI

from resume_engine.config.settings import DEFAULT_OPENAI_MODEL
from resume_engine.models.jd_blueprint import JDBlueprint
from resume_engine.models.resume_schema import OpenAIResumeJSON, ResumeJSON
from resume_engine.models.resume_strategy import ResumeStrategy, VariantStrategy


def rewrite_targeted_resume_parts(
    client: OpenAI,
    blueprint: JDBlueprint,
    strategy: ResumeStrategy,
    variant: VariantStrategy,
    resume: ResumeJSON,
    repair_plan: dict,
    model: str | None = None,
) -> ResumeJSON:
    if not repair_plan.get("required"):
        return resume

    system = """
You are a targeted resume repair engine.

Repair only the failing areas described in repair_plan.
Do not regenerate the entire resume conceptually.
Do not add technologies outside allowed_technologies.
Do not invent candidate history, employers, certifications, metrics, or tools.
Return the complete repaired OpenAIResumeJSON so downstream validators can rerun.
technical_skills must be a list of category objects, each with category and skills.
"""
    payload = {
        "jd_blueprint": blueprint.as_prompt_payload(),
        "resume_strategy": strategy.model_dump(),
        "variant_strategy": variant.model_dump(),
        "current_resume": resume.model_dump(),
        "repair_plan": repair_plan,
        "allowed_technologies": blueprint.generation_contract.allowed_technologies,
    }

    response = client.responses.parse(
        model=model or os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload, indent=2, ensure_ascii=False)},
        ],
        text_format=OpenAIResumeJSON,
    )

    if response.output_parsed is None:
        raise RuntimeError("Targeted repair returned no structured ResumeJSON.")

    repaired = response.output_parsed.to_resume_json()
    repaired.variant_id = resume.variant_id
    repaired.source_blueprint_hash = resume.source_blueprint_hash
    return repaired
