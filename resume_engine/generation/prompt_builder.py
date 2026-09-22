import json

from resume_engine.models.jd_blueprint import JDBlueprint
from resume_engine.models.resume_strategy import ResumeStrategy, VariantStrategy


def build_resume_generation_prompt(
    blueprint: JDBlueprint,
    strategy: ResumeStrategy,
    variant: VariantStrategy,
    generation_context: dict,
) -> list[dict[str, str]]:
    system = """
You are a structured resume JSON generator.

You must generate exactly one targeted resume variant as OpenAIResumeJSON.

STRICT RULES:
1. If generation_mode is TEMPLATE, create JD-centric resume template content using resume_seed structure.
2. If generation_mode is CANDIDATE, use only candidate facts supplied in candidate_profile.
3. In TEMPLATE mode, do not present template content as verified personal truth.
4. Preserve resume_seed company names, order, and title style.
5. Use only technologies listed in blueprint.generation_contract.allowed_technologies.
6. Do not invent degrees, certifications, dates, metrics, tools, or technologies.
7. If a metric is not supplied, write an impact statement without fabricated numbers.
8. Keep the resume centered on the blueprint target role and job family.
9. Variants may differ in emphasis only; they may not introduce unrelated stacks.
10. P1 skills must appear prominently in summary, skills, and experience when placement requires it.
11. P2 skills must appear in skills and experience when placement requires it.
12. P4 skills are optional/supporting only and must not dominate the resume.
13. Return only the requested structured JSON.
14. Do not populate skill_provenance; the deterministic engine will attach it after generation.
15. technical_skills must be a list of category objects, each with category and skills.
"""

    user = {
        "jd_blueprint": blueprint.as_prompt_payload(),
        "resume_strategy": strategy.model_dump(),
        "variant_strategy": variant.model_dump(),
        "generation_context": generation_context,
        "output_requirements": {
            "format": "OpenAIResumeJSON",
            "include_sections": [
                "target_title",
                "summary",
                "technical_skills as category/skills objects",
                "experience",
                "projects",
                "certifications",
            ],
            "bullet_style": "concise, ATS-safe, achievement-oriented, no markdown bullets",
            "provenance": "leave skill_provenance empty; deterministic validation adds provenance",
        },
    }

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user, indent=2, ensure_ascii=False)},
    ]
