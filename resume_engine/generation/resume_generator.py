import json
from pathlib import Path

from resume_engine.config.settings import GENERATED_STORAGE_DIR, ensure_storage_dirs
from resume_engine.generation.openai_generator import generate_resume_with_openai
from resume_engine.generation.provenance import attach_skill_provenance
from resume_engine.models.jd_blueprint import JDBlueprint
from resume_engine.models.resume_schema import ResumeJSON
from resume_engine.models.resume_strategy import ResumeStrategy, VariantStrategy


def save_generated_resume(resume: ResumeJSON) -> Path:
    ensure_storage_dirs()
    variant_id = resume.variant_id or "variant"
    blueprint_hash = resume.source_blueprint_hash or "unknown_blueprint"
    path = GENERATED_STORAGE_DIR / f"{blueprint_hash}_{variant_id}_resume.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(resume.model_dump(), f, indent=2, ensure_ascii=False)
    return path


def generate_resume_variant(
    client,
    blueprint: JDBlueprint,
    strategy: ResumeStrategy,
    variant: VariantStrategy,
    generation_context: dict,
    model: str | None = None,
) -> tuple[ResumeJSON, Path]:
    resume = generate_resume_with_openai(
        client=client,
        blueprint=blueprint,
        strategy=strategy,
        variant=variant,
        generation_context=generation_context,
        model=model,
    )
    resume = attach_skill_provenance(blueprint, resume)
    path = save_generated_resume(resume)
    return resume, path
