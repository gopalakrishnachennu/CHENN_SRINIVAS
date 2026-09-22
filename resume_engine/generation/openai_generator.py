import os

from openai import OpenAI

from resume_engine.config.settings import DEFAULT_OPENAI_MODEL, load_local_environment
from resume_engine.generation.prompt_builder import build_resume_generation_prompt
from resume_engine.models.jd_blueprint import JDBlueprint
from resume_engine.models.resume_schema import OpenAIResumeJSON, ResumeJSON
from resume_engine.models.resume_strategy import ResumeStrategy, VariantStrategy


def build_openai_client() -> OpenAI:
    load_local_environment()
    return OpenAI()


def generate_resume_with_openai(
    client: OpenAI,
    blueprint: JDBlueprint,
    strategy: ResumeStrategy,
    variant: VariantStrategy,
    generation_context: dict,
    model: str | None = None,
) -> ResumeJSON:
    messages = build_resume_generation_prompt(
        blueprint=blueprint,
        strategy=strategy,
        variant=variant,
        generation_context=generation_context,
    )

    response = client.responses.parse(
        model=model or os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
        input=messages,
        text_format=OpenAIResumeJSON,
    )

    if response.output_parsed is None:
        raise RuntimeError("OpenAI resume generation returned no structured ResumeJSON.")

    resume = response.output_parsed.to_resume_json()
    resume.variant_id = variant.variant_id
    resume.source_blueprint_hash = blueprint.jd_hash
    return resume
