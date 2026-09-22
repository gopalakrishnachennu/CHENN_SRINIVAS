import json
from pathlib import Path

from resume_engine.config import thresholds
from resume_engine.config.settings import VALIDATED_STORAGE_DIR, ensure_storage_dirs
from resume_engine.generation.provenance import attach_skill_provenance
from resume_engine.generation.openai_generator import build_openai_client
from resume_engine.generation.resume_generator import generate_resume_variant, save_generated_resume
from resume_engine.learning.failure_store import save_failure_record
from resume_engine.learning.outcome_store import save_learning_outcome
from resume_engine.learning.pattern_updater import update_learning_patterns
from resume_engine.models.jd_blueprint import JDBlueprint
from resume_engine.models.resume_schema import ResumeJSON
from resume_engine.models.resume_seed import ResumeSeed
from resume_engine.models.resume_strategy import ResumeStrategy, VariantStrategy
from resume_engine.models.validation_schema import ValidationBundle, ValidatorResult
from resume_engine.repair.repair_validator import attach_repair_plan, should_repair
from resume_engine.repair.targeted_rewriter import rewrite_targeted_resume_parts
from resume_engine.reports.report_writer import save_validation_reports
from resume_engine.scoring.score_engine import calculate_score
from resume_engine.strategy.strategy_builder import build_strategy, save_strategy
from resume_engine.strategy.variant_planner import create_variants
from resume_engine.validation.ats_validator import validate_ats
from resume_engine.validation.ai_tool_placement_validator import validate_ai_tool_placement
from resume_engine.validation.blueprint_validator import validate_blueprint_ready
from resume_engine.validation.coverage_validator import validate_coverage
from resume_engine.validation.duplicate_validator import validate_duplicates
from resume_engine.validation.hybrid_family_validator import validate_hybrid_family_retention
from resume_engine.validation.laya_validator import validate_with_laya
from resume_engine.validation.responsibility_validator import validate_responsibilities
from resume_engine.validation.role_drift_validator import validate_role_drift
from resume_engine.validation.technology_firewall import validate_technology_firewall
from resume_engine.validation.variant_similarity_validator import validate_variant_similarity


def load_candidate_profile(path: str | Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_resume_seed(path: str | Path) -> ResumeSeed:
    return ResumeSeed.from_json_file(str(path))


def build_generation_context(
    resume_seed_path: str | Path | None,
    candidate_profile_path: str | Path | None,
) -> dict:
    if candidate_profile_path:
        return {
            "generation_mode": "CANDIDATE",
            "candidate_profile": load_candidate_profile(candidate_profile_path),
            "template_policy": "personalized resume using truthful candidate facts only",
        }

    if resume_seed_path is None:
        resume_seed_path = "resume_seed.json"

    return {
        "generation_mode": "TEMPLATE",
        "resume_seed": load_resume_seed(resume_seed_path).model_dump(),
        "template_policy": (
            "JD-centric optimized resume template. Content is a template draft, "
            "not verified personal truth until a user reviews and adopts it."
        ),
    }


def load_laya_agent():
    from jd_blueprint_engine import load_laya_agent as phase1_load_laya_agent

    return phase1_load_laya_agent()


def _resume_id(blueprint: JDBlueprint, variant_id: str, suffix: str = "") -> str:
    return f"{blueprint.jd_hash}_{variant_id}{suffix}".strip("_")


def run_validators(
    blueprint: JDBlueprint,
    resume: ResumeJSON,
    laya_agent,
    resume_id: str,
) -> ValidationBundle:
    results: list[ValidatorResult] = [
        validate_blueprint_ready(blueprint),
        validate_technology_firewall(blueprint, resume),
        validate_coverage(blueprint, resume),
        validate_ai_tool_placement(blueprint, resume),
        validate_responsibilities(blueprint, resume),
        validate_hybrid_family_retention(blueprint, resume),
        validate_duplicates(resume),
        validate_role_drift(blueprint, resume),
        validate_ats(resume),
    ]

    if laya_agent is not None:
        results.append(validate_with_laya(blueprint, resume, laya_agent))

    optimization_score, subscores = calculate_score(results)
    hard_failed = any(
        issue.severity == "error"
        for result in results
        for issue in result.issues
    )
    passed = not hard_failed and optimization_score >= thresholds.PASS_SCORE_MIN

    bundle = ValidationBundle(
        variant_id=resume.variant_id or "unknown_variant",
        resume_id=resume_id,
        passed=passed,
        optimization_score=optimization_score,
        action="PASS" if passed else "REPAIR_REQUIRED",
        subscores=subscores,
        validator_results=results,
    )
    return attach_repair_plan(bundle)


def save_validated_resume(resume: ResumeJSON, resume_id: str) -> Path:
    ensure_storage_dirs()
    path = VALIDATED_STORAGE_DIR / f"{resume_id}_final_resume.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(resume.model_dump(), f, indent=2, ensure_ascii=False)
    return path


def process_variant(
    client,
    blueprint: JDBlueprint,
    strategy: ResumeStrategy,
    variant: VariantStrategy,
    generation_context: dict,
    laya_agent,
    model: str | None = None,
    repair: bool = True,
) -> dict:
    resume, generated_path = generate_resume_variant(
        client=client,
        blueprint=blueprint,
        strategy=strategy,
        variant=variant,
        generation_context=generation_context,
        model=model,
    )

    before_id = _resume_id(blueprint, variant.variant_id, "before_repair")
    before_bundle = run_validators(blueprint, resume, laya_agent, before_id)
    before_report_json, before_report_txt = save_validation_reports(blueprint, before_bundle)

    final_resume = resume
    final_bundle = before_bundle
    repaired_path = None
    after_report_json = None
    after_report_txt = None

    if repair and should_repair(before_bundle):
        final_resume = rewrite_targeted_resume_parts(
            client=client,
            blueprint=blueprint,
            strategy=strategy,
            variant=variant,
            resume=resume,
            repair_plan=before_bundle.repair_plan,
            model=model,
        )
        final_resume.variant_id = variant.variant_id
        final_resume.source_blueprint_hash = blueprint.jd_hash
        final_resume = attach_skill_provenance(blueprint, final_resume)
        repaired_path = save_generated_resume(final_resume)

        after_id = _resume_id(blueprint, variant.variant_id, "after_repair")
        final_bundle = run_validators(blueprint, final_resume, laya_agent, after_id)
        after_report_json, after_report_txt = save_validation_reports(blueprint, final_bundle)

    final_resume_id = _resume_id(blueprint, variant.variant_id, "final")
    final_resume_path = save_validated_resume(final_resume, final_resume_id)

    failures = [
        issue.code
        for result in final_bundle.validator_results
        for issue in result.issues
    ]

    learning_record = {
        "jd_hash": blueprint.jd_hash,
        "job_family": blueprint.job.primary_family,
        "primary_family": blueprint.job.primary_family,
        "secondary_family": blueprint.job.secondary_family,
        "strategy": strategy.strategy_id,
        "variant_id": variant.variant_id,
        "variant_positioning": variant.positioning,
        "score_before_repair": before_bundle.optimization_score,
        "score_after_repair": final_bundle.optimization_score,
        "failures": failures,
        "repairs": before_bundle.repair_plan if repaired_path else {},
        "successful_pattern": final_bundle.passed,
    }
    save_learning_outcome(learning_record)

    if failures:
        save_failure_record(learning_record)

    return {
        "variant_id": variant.variant_id,
        "variant_positioning": variant.positioning,
        "generated_resume": str(generated_path),
        "repaired_resume": str(repaired_path) if repaired_path else None,
        "final_resume": str(final_resume_path),
        "before_validation_json": str(before_report_json),
        "before_validation_txt": str(before_report_txt),
        "after_validation_json": str(after_report_json) if after_report_json else None,
        "after_validation_txt": str(after_report_txt) if after_report_txt else None,
        "score_before_repair": before_bundle.optimization_score,
        "score_after_repair": final_bundle.optimization_score,
        "passed": final_bundle.passed,
        "action": final_bundle.action,
    }


def run_phase2_pipeline(
    blueprint_path: str | Path,
    candidate_profile_path: str | Path | None = None,
    resume_seed_path: str | Path | None = "resume_seed.json",
    variant_limit: int = 5,
    model: str | None = None,
    repair: bool = True,
    use_laya: bool = True,
) -> dict:
    ensure_storage_dirs()
    blueprint = JDBlueprint.from_json_file(str(blueprint_path))
    generation_context = build_generation_context(resume_seed_path, candidate_profile_path)

    strategy = build_strategy(blueprint)
    strategy_path = save_strategy(strategy)
    variants = create_variants(blueprint, strategy)[:variant_limit]

    client = build_openai_client()
    laya_agent = load_laya_agent() if use_laya else None

    variant_results = []
    for variant in variants:
        variant_results.append(
            process_variant(
                client=client,
                blueprint=blueprint,
                strategy=strategy,
                variant=variant,
                generation_context=generation_context,
                laya_agent=laya_agent,
                model=model,
                repair=repair,
            )
        )

    final_resumes = []
    for item in variant_results:
        with open(item["final_resume"], "r", encoding="utf-8") as f:
            final_resumes.append(ResumeJSON.model_validate(json.load(f)))
    variant_similarity_result = validate_variant_similarity(final_resumes) if len(final_resumes) > 1 else None

    learning_update = update_learning_patterns()

    result = {
        "phase": "Phase 2",
        "generation_mode": generation_context["generation_mode"],
        "blueprint": str(blueprint_path),
        "resume_seed": str(resume_seed_path) if resume_seed_path else None,
        "candidate_profile": str(candidate_profile_path) if candidate_profile_path else None,
        "strategy": str(strategy_path),
        "variants_processed": len(variant_results),
        "variant_results": variant_results,
        "variant_diversity": variant_similarity_result.model_dump() if variant_similarity_result else None,
        "learning_update": learning_update,
    }

    if variant_similarity_result is not None:
        save_learning_outcome(
            {
                "record_type": "variant_diversity",
                "jd_hash": blueprint.jd_hash,
                "job_family": blueprint.job.primary_family,
                "primary_family": blueprint.job.primary_family,
                "secondary_family": blueprint.job.secondary_family,
                "hybrid_status": blueprint.job.hybrid_probability >= 0.55 and blueprint.job.secondary_family != "none",
                "variant_strategy": "all_variants",
                "variant_diversity_result": variant_similarity_result.model_dump(),
            }
        )

    summary_path = VALIDATED_STORAGE_DIR / f"{blueprint.jd_hash}_phase2_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    result["summary_path"] = str(summary_path)
    return result
