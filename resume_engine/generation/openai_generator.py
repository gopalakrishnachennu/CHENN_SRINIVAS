import os

from resume_engine.config.settings import (
    DEFAULT_OPENAI_MODEL,
    PROMPT_VERSION,
    load_local_environment,
)
from resume_engine.generation.prompt_builder import build_resume_generation_prompt
from resume_engine.llm.client import LLMClient, build_llm_client
from resume_engine.models.jd_blueprint import JDBlueprint
from resume_engine.models.resume_schema import OpenAIResumeJSON, ResumeJSON
from resume_engine.models.resume_strategy import ResumeStrategy, VariantStrategy


def build_openai_client() -> LLMClient:
    """Backward-compatible factory; returns Wave 4 LLMClient wrapper."""
    load_local_environment()
    return build_llm_client()


def generate_resume_with_openai(
    client: LLMClient | object,
    blueprint: JDBlueprint,
    strategy: ResumeStrategy,
    variant: VariantStrategy,
    generation_context: dict,
    model: str | None = None,
    run_id: str | None = None,
) -> ResumeJSON:
    messages = build_resume_generation_prompt(
        blueprint=blueprint,
        strategy=strategy,
        variant=variant,
        generation_context=generation_context,
    )

    resolved_model = model or os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
    if isinstance(client, LLMClient):
        response = client.parse(
            model=resolved_model,
            input=messages,
            text_format=OpenAIResumeJSON,
            run_id=run_id,
            prompt_version=PROMPT_VERSION,
            operation="resume_generation",
        )
    else:
        response = client.responses.parse(
            model=resolved_model,
            input=messages,
            text_format=OpenAIResumeJSON,
        )

    if response.output_parsed is None:
        raise RuntimeError("OpenAI resume generation returned no structured ResumeJSON.")

    resume = response.output_parsed.to_resume_json()
    resume.variant_id = variant.variant_id
    resume.source_blueprint_hash = blueprint.jd_hash
    return resume
