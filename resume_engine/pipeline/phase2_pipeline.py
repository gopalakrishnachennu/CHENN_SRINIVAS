import contextlib
import json
from pathlib import Path
from typing import Any, Callable

from resume_engine.config import thresholds
from resume_engine.config.settings import (
    DEFAULT_OPENAI_MODEL,
    PROJECT_ROOT,
    PROMPT_VERSION,
    ensure_storage_dirs,
    portable_path,
)
from resume_engine.generation.bullet_enrichment import (
    apply_certification_policy,
    attach_bullet_metadata,
)
from resume_engine.generation.openai_generator import build_openai_client
from resume_engine.generation.provenance import attach_skill_provenance
from resume_engine.generation.resume_generator import generate_resume_with_openai
from resume_engine.learning.failure_store import save_failure_record
from resume_engine.learning.fingerprint_store import save_fingerprint, validate_cross_run_uniqueness
from resume_engine.learning.outcome_builder import build_learning_outcome
from resume_engine.learning.outcome_store import save_learning_outcome
from resume_engine.learning.pattern_updater import update_learning_patterns
from resume_engine.learning.strategy_memory import retrieve_strategy_insights
from resume_engine.models.jd_blueprint import JDBlueprint
from resume_engine.models.resume_schema import ResumeJSON
from resume_engine.models.resume_seed import ResumeSeed
from resume_engine.models.resume_strategy import ResumeStrategy, VariantStrategy
from resume_engine.models.validation_schema import ValidationBundle, ValidatorResult
from resume_engine.repair.repair_validator import attach_repair_plan, should_repair
from resume_engine.repair.targeted_rewriter import rewrite_targeted_resume_parts
from resume_engine.repair.version_selector import select_best_resume_version
from resume_engine.scoring.score_engine import build_variant_diagnostics, calculate_score
from resume_engine.storage.run_store import (
    create_run_paths,
    relative,
    save_pipeline_error_report,
    save_raw_resume,
    save_rejected_resume_artifact,
    save_repaired_resume,
    save_strategy_artifact,
    save_validated_resume_artifact,
    save_validation_bundle_reports,
    write_run_metadata,
)
from resume_engine.strategy.strategy_builder import build_strategy, save_strategy
from resume_engine.strategy.variant_planner import create_variants
from resume_engine.validation.ai_tool_placement_validator import validate_ai_tool_placement
from resume_engine.validation.ats_validator import validate_ats
from resume_engine.validation.blueprint_validator import validate_blueprint_ready
from resume_engine.validation.coverage_validator import validate_coverage
from resume_engine.validation.duplicate_validator import validate_duplicates
from resume_engine.validation.hybrid_family_validator import validate_hybrid_family_retention
from resume_engine.validation.laya_validator import validate_with_laya
from resume_engine.validation.p4_usage_validator import validate_p4_usage
from resume_engine.validation.responsibility_validator import validate_responsibilities
from resume_engine.validation.role_drift_validator import validate_role_drift
from resume_engine.validation.technology_firewall import validate_technology_firewall
from resume_engine.validation.variant_regeneration import find_duplicate_pairs
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


def _enrich_resume(
    blueprint: JDBlueprint,
    resume: ResumeJSON,
    generation_context: dict,
) -> ResumeJSON:
    resume = attach_skill_provenance(blueprint, resume)
    resume = attach_bullet_metadata(blueprint, resume)
    resume = apply_certification_policy(
        blueprint,
        resume,
        generation_mode=generation_context.get("generation_mode", "TEMPLATE"),
        candidate_profile=generation_context.get("candidate_profile"),
    )
    return resume


def run_validators(
    blueprint: JDBlueprint,
    resume: ResumeJSON,
    laya_agent,
    resume_id: str,
    run_id: str | None = None,
    check_cross_run: bool = True,
    generation_mode: str = "TEMPLATE",
    candidate_profile: dict | None = None,
) -> ValidationBundle:
    results: list[ValidatorResult] = [
        validate_blueprint_ready(blueprint),
        validate_technology_firewall(blueprint, resume),
        validate_coverage(blueprint, resume),
        validate_p4_usage(blueprint, resume),
        validate_ai_tool_placement(blueprint, resume),
        validate_responsibilities(blueprint, resume),
        validate_hybrid_family_retention(blueprint, resume),
        validate_duplicates(resume),
        validate_role_drift(blueprint, resume),
        validate_ats(resume),
    ]

    if check_cross_run and run_id:
        results.append(validate_cross_run_uniqueness(resume, blueprint.jd_hash, run_id))

    if laya_agent is not None:
        responsibility_result = next(
            (item for item in results if item.name == "responsibility_validator"),
            None,
        )
        uncovered = []
        if responsibility_result:
            uncovered = list(
                responsibility_result.details.get("uncovered_responsibility_ids") or []
            )
        results.append(
            validate_with_laya(
                blueprint,
                resume,
                laya_agent,
                uncovered_responsibility_ids=uncovered,
            )
        )

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
    return attach_repair_plan(
        bundle,
        blueprint=blueprint,
        generation_mode=generation_mode,
        candidate_profile=candidate_profile,
        resume=resume,
    )


def process_variant(
    client,
    blueprint: JDBlueprint,
    strategy: ResumeStrategy,
    variant: VariantStrategy,
    generation_context: dict,
    laya_agent,
    run_paths,
    model: str | None = None,
    repair: bool = True,
    *,
    attempt_no: int = 1,
    persist_learning: bool = False,
    regen_reason: str | None = None,
) -> dict:
    generation_mode = generation_context.get("generation_mode", "TEMPLATE")
    candidate_profile = generation_context.get("candidate_profile")
    stage = "generation"
    try:
        resume = generate_resume_with_openai(
            client=client,
            blueprint=blueprint,
            strategy=strategy,
            variant=variant,
            generation_context=generation_context,
            model=model,
            run_id=run_paths.run_id,
        )
        resume = _enrich_resume(blueprint, resume, generation_context)
        stage = "save_raw"
        raw_path = save_raw_resume(
            run_paths, variant.variant_id, resume, attempt_no=attempt_no
        )

        stage = "validation_before_repair"
        before_id = _resume_id(blueprint, variant.variant_id, f"before_repair_a{attempt_no}")
        before_bundle = run_validators(
            blueprint,
            resume,
            laya_agent,
            before_id,
            run_id=run_paths.run_id,
            check_cross_run=True,
            generation_mode=generation_mode,
            candidate_profile=candidate_profile,
        )
        before_report_json, before_report_txt = save_validation_bundle_reports(
            run_paths,
            blueprint,
            before_bundle,
            "before_repair",
            attempt_no=attempt_no,
        )

        repaired_resume = None
        repaired_path = None
        after_bundle = None
        after_report_json = None
        after_report_txt = None

        if repair and should_repair(before_bundle):
            stage = "targeted_repair"
            repaired_resume = rewrite_targeted_resume_parts(
                client=client,
                blueprint=blueprint,
                strategy=strategy,
                variant=variant,
                resume=resume,
                repair_plan=before_bundle.repair_plan,
                model=model,
                run_id=run_paths.run_id,
            )
            repaired_resume.variant_id = variant.variant_id
            repaired_resume.source_blueprint_hash = blueprint.jd_hash
            repaired_resume = _enrich_resume(blueprint, repaired_resume, generation_context)
            repaired_path = save_repaired_resume(
                run_paths, variant.variant_id, repaired_resume, attempt_no=attempt_no
            )

            stage = "validation_after_repair"
            after_id = _resume_id(blueprint, variant.variant_id, f"after_repair_a{attempt_no}")
            after_bundle = run_validators(
                blueprint,
                repaired_resume,
                laya_agent,
                after_id,
                run_id=run_paths.run_id,
                check_cross_run=True,
                generation_mode=generation_mode,
                candidate_profile=candidate_profile,
            )
            after_report_json, after_report_txt = save_validation_bundle_reports(
                run_paths,
                blueprint,
                after_bundle,
                "after_repair",
                attempt_no=attempt_no,
            )

        selection = select_best_resume_version(
            raw_resume=resume,
            raw_bundle=before_bundle,
            repaired_resume=repaired_resume,
            repaired_bundle=after_bundle,
        )

        # Candidate gaps remaining after repair keep the variant from validating.
        gaps = selection.bundle.repair_plan.get("unresolved_required_candidate_gaps") or []
        if gaps:
            selection.bundle.passed = False
            if selection.status == "VALIDATED":
                selection.status = "FAILED_VALIDATION"

        final_resume_path = None
        rejected_resume_path = None
        status = selection.status
        passed = selection.status == "VALIDATED" and selection.resume is not None
        diagnostics = build_variant_diagnostics(
            selection.resume or resume,
            variant,
            selection.bundle.subscores,
        )

        stage = "finalize"
        if passed and selection.resume is not None:
            final_resume_path = save_validated_resume_artifact(
                run_paths,
                variant.variant_id,
                selection.resume,
                attempt_no=attempt_no,
            )
            final_report_json, final_report_txt = save_validation_bundle_reports(
                run_paths,
                blueprint,
                selection.bundle,
                "final",
                attempt_no=attempt_no,
            )
        else:
            artifact_for_reject = selection.resume or repaired_resume or resume
            rejected_resume_path = save_rejected_resume_artifact(
                run_paths,
                variant.variant_id,
                artifact_for_reject,
                attempt_no=attempt_no,
            )
            final_report_json, final_report_txt = save_validation_bundle_reports(
                run_paths,
                blueprint,
                selection.bundle,
                "rejected",
                attempt_no=attempt_no,
            )
            status = "FAILED_VALIDATION"
            passed = False

        resolved_model = model or DEFAULT_OPENAI_MODEL
        learning_record = build_learning_outcome(
            blueprint=blueprint,
            variant=variant,
            run_id=run_paths.run_id,
            strategy_id=strategy.strategy_id,
            before_bundle=before_bundle,
            selection_bundle=selection.bundle,
            passed=passed,
            status=status,
            repaired=bool(repaired_path),
            regression_recorded=selection.regression_recorded,
            selection_notes=selection.notes,
            diagnostics=diagnostics,
            model=resolved_model,
            prompt_version=PROMPT_VERSION,
        )
        learning_record.update(
            {
                "attempt_no": attempt_no,
                "is_final_selection": False,
                "superseded": False,
                "regen_reason": regen_reason,
                "eligible_for_learning": False,
            }
        )
        # Defer eligible learning until regeneration settles unless explicitly requested.
        if persist_learning:
            learning_record["is_final_selection"] = True
            learning_record["superseded"] = False
            # Clear deferred-ineligible marker before computing eligibility.
            learning_record.pop("eligible_for_learning", None)
            from resume_engine.learning.eligibility import is_record_eligible_for_learning

            learning_record["eligible_for_learning"] = is_record_eligible_for_learning(
                learning_record
            )
            save_learning_outcome(learning_record)
            if passed:
                save_fingerprint(
                    jd_hash=blueprint.jd_hash,
                    run_id=run_paths.run_id,
                    variant_id=variant.variant_id,
                    resume=selection.resume,
                    passed=True,
                )

        return {
            "variant_id": variant.variant_id,
            "variant_positioning": variant.positioning,
            "run_id": run_paths.run_id,
            "status": status,
            "passed": passed,
            "attempt_no": attempt_no,
            "is_final_selection": learning_record.get("is_final_selection", False),
            "superseded": learning_record.get("superseded", False),
            "regen_reason": regen_reason,
            "generated_resume": relative(raw_path),
            "raw_resume": relative(raw_path),
            "repaired_resume": relative(repaired_path) if repaired_path else None,
            "final_resume": relative(final_resume_path) if final_resume_path else None,
            "rejected_resume": relative(rejected_resume_path) if rejected_resume_path else None,
            "before_validation_json": relative(before_report_json),
            "before_validation_txt": relative(before_report_txt),
            "after_validation_json": relative(after_report_json) if after_report_json else None,
            "after_validation_txt": relative(after_report_txt) if after_report_txt else None,
            "final_validation_json": relative(final_report_json),
            "final_validation_txt": relative(final_report_txt),
            "score_before_repair": before_bundle.optimization_score,
            "score_after_repair": (
                after_bundle.optimization_score
                if after_bundle is not None
                else before_bundle.optimization_score
            ),
            "action": selection.bundle.action,
            "selection_notes": selection.notes,
            "repair_score_regression": selection.regression_recorded,
            "diagnostics": diagnostics,
            "_resume_object": selection.resume if passed else None,
            "_variant_object": variant,
            "_learning_record": learning_record,
        }
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as exc:  # noqa: BLE001 — isolate per-variant failures
        error_path = save_pipeline_error_report(
            run_paths,
            variant_id=variant.variant_id,
            stage=stage,
            error=exc,
            attempt_no=attempt_no,
        )
        learning_record = {
            "run_id": run_paths.run_id,
            "jd_hash": blueprint.jd_hash,
            "variant_id": variant.variant_id,
            "variant_positioning": variant.positioning,
            "attempt_no": attempt_no,
            "is_final_selection": True,
            "superseded": False,
            "passed": False,
            "status": "PIPELINE_ERROR",
            "eligible_for_learning": False,
            "successful_pattern": False,
            "failure_codes": [getattr(exc, "code", type(exc).__name__)],
            "stage": stage,
            "error_type": type(exc).__name__,
            "message": str(exc)[:500],
        }
        return {
            "variant_id": variant.variant_id,
            "variant_positioning": variant.positioning,
            "run_id": run_paths.run_id,
            "status": "PIPELINE_ERROR",
            "passed": False,
            "attempt_no": attempt_no,
            "is_final_selection": True,
            "superseded": False,
            "final_resume": None,
            "pipeline_error_report": relative(error_path),
            "eligible_for_learning": False,
            "diagnostics": {},
            "_resume_object": None,
            "_variant_object": variant,
            "_learning_record": learning_record,
            "error_type": type(exc).__name__,
            "error_message": str(exc)[:500],
            "stage": stage,
        }


def run_phase2_pipeline(
    blueprint_path: str | Path,
    candidate_profile_path: str | Path | None = None,
    resume_seed_path: str | Path | None = "resume_seed.json",
    variant_limit: int = 5,
    model: str | None = None,
    repair: bool = True,
    use_laya: bool = True,
    run_id: str | None = None,
    export_formats: list[str] | None = None,
    progress_callback: Callable[[str, str, dict[str, Any] | None], None] | None = None,
    single_call: bool = False,
) -> dict:
    def progress(stage: str, message: str, detail: dict[str, Any] | None = None) -> None:
        if progress_callback is None:
            return
        with contextlib.suppress(Exception):
            progress_callback(stage, message, detail or {})

    ensure_storage_dirs()
    progress("load_blueprint", "Loading JD blueprint and candidate evidence.", None)
    blueprint = JDBlueprint.from_json_file(str(blueprint_path))
    generation_context = build_generation_context(resume_seed_path, candidate_profile_path)

    run_paths = create_run_paths(blueprint.jd_hash, run_id=run_id)

    progress("strategy", "Creating resume strategy and variant plan.", {"jd_hash": blueprint.jd_hash})
    strategy = build_strategy(blueprint)
    # Keep legacy flat strategy write for backward compatibility, plus run-scoped copy.
    legacy_strategy_path = save_strategy(strategy)
    strategy_path = save_strategy_artifact(run_paths, strategy)
    learning_insights = retrieve_strategy_insights(blueprint)
    variants = create_variants(
        blueprint,
        strategy,
        learning_insights=learning_insights,
    )[:variant_limit]
    if single_call:
        variants = variants[:1]
    progress(
        "strategy_ready",
        (
            "Single-resume plan ready: one OpenAI generation call."
            if single_call
            else f"Strategy ready with {len(variants)} variant(s)."
        ),
        {"variant_count": len(variants), "single_call": single_call},
    )

    # Phase 2.8: shadow ranking only — production order unchanged.
    online_shadow_decisions = 0
    online_fallbacks = 0
    with contextlib.suppress(Exception):
        from resume_engine.learning.online.shadow_runner import (
            record_shadow_decisions_for_variants,
        )

        decisions = record_shadow_decisions_for_variants(
            blueprint=blueprint,
            production_variants=[(v.variant_id, v.positioning) for v in variants],
            run_id=run_paths.run_id,
        )
        online_shadow_decisions = len(decisions)
        if not decisions:
            online_fallbacks += 1

    resolved_model = model or DEFAULT_OPENAI_MODEL
    write_run_metadata(
        run_paths,
        {
            "generation_mode": generation_context["generation_mode"],
            "variant_count": len(variants),
            "single_call": single_call,
            "model": resolved_model,
            "blueprint_version": blueprint.blueprint_version,
            "prompt_version": PROMPT_VERSION,
            "blueprint_path": portable_path(blueprint_path),
            "legacy_strategy_path": portable_path(legacy_strategy_path),
            "learning": {
                "applied": learning_insights.get("applied"),
                "eligible_sample_count": learning_insights.get("eligible_sample_count"),
                "min_sample_count": learning_insights.get("min_sample_count"),
                "scope": learning_insights.get("scope"),
            },
        },
    )

    progress(
        "openai_setup",
        f"Preparing OpenAI client for model {resolved_model}.",
        {"model": resolved_model, "variant_count": len(variants)},
    )
    client = build_openai_client(max_retries=0) if single_call else build_openai_client()
    laya_agent = load_laya_agent() if use_laya else None

    variant_by_id = {variant.variant_id: variant for variant in variants}
    attempt_nos: dict[str, int] = {variant.variant_id: 1 for variant in variants}
    variant_results = []
    for index, variant in enumerate(variants, start=1):
        progress(
            f"generate_variant_{index}",
            f"Calling OpenAI and validating variant {index} of {len(variants)}.",
            {"variant_id": variant.variant_id, "index": index, "total": len(variants), "model": resolved_model},
        )
        variant_results.append(
            process_variant(
                client=client,
                blueprint=blueprint,
                strategy=strategy,
                variant=variant,
                generation_context=generation_context,
                laya_agent=laya_agent,
                run_paths=run_paths,
                model=model,
                repair=repair and not single_call,
                attempt_no=1,
                persist_learning=False,
            )
        )
        progress(
            f"variant_{index}_complete",
            f"Variant {index} completed.",
            {"variant_id": variant.variant_id, "index": index, "total": len(variants)},
        )

    # Cross-variant auto regeneration: regenerate only weaker duplicates.
    regen_events = []
    regen_counts: dict[str, int] = {variant.variant_id: 0 for variant in variants}
    for _ in range(0 if single_call else thresholds.VARIANT_REGEN_MAX):
        passed_items = [item for item in variant_results if item.get("passed") and item.get("_resume_object")]
        if len(passed_items) < 2:
            break
        resumes = [item["_resume_object"] for item in passed_items]
        scores = {
            item["variant_id"]: item.get("score_after_repair", 0.0) for item in passed_items
        }
        pairs = find_duplicate_pairs(resumes, scores, variant_by_id)
        if not pairs:
            break
        weaker_ids = []
        for pair in pairs:
            weaker = pair["weaker_variant_id"]
            if regen_counts.get(weaker, 0) >= thresholds.VARIANT_REGEN_MAX:
                continue
            if weaker not in weaker_ids:
                weaker_ids.append(weaker)
        if not weaker_ids:
            break
        for weaker_id in weaker_ids:
            progress(
                "regenerate_variant",
                f"Regenerating duplicate-heavy variant {weaker_id}.",
                {"variant_id": weaker_id},
            )
            # Mark prior attempt as superseded (diagnostic only; not eligible).
            for item in variant_results:
                if item["variant_id"] == weaker_id:
                    item["superseded"] = True
                    item["is_final_selection"] = False
                    prior = item.get("_learning_record") or {}
                    prior["superseded"] = True
                    prior["is_final_selection"] = False
                    prior["eligible_for_learning"] = False
                    prior["regen_reason"] = "VARIANT_SIMILARITY"
                    item["_learning_record"] = prior
                    # Persist superseded diagnostic record once.
                    save_learning_outcome(prior)
                    break

            variant = variant_by_id[weaker_id]
            regen_counts[weaker_id] += 1
            attempt_nos[weaker_id] = regen_counts[weaker_id] + 1
            regenerated = process_variant(
                client=client,
                blueprint=blueprint,
                strategy=strategy,
                variant=variant,
                generation_context=generation_context,
                laya_agent=laya_agent,
                run_paths=run_paths,
                model=model,
                repair=repair,
                attempt_no=attempt_nos[weaker_id],
                persist_learning=False,
                regen_reason="VARIANT_SIMILARITY",
            )
            regenerated["regenerated"] = True
            regenerated["regen_attempt"] = regen_counts[weaker_id]
            regen_events.append(
                {
                    "variant_id": weaker_id,
                    "attempt": attempt_nos[weaker_id],
                    "passed": regenerated.get("passed"),
                }
            )
            variant_results = [
                regenerated if item["variant_id"] == weaker_id else item
                for item in variant_results
            ]

    progress("learning", "Recording final validation and shadow-learning observations.", None)
    # After regeneration settles: persist exactly one final learning outcome per variant.
    from resume_engine.learning.eligibility import is_record_eligible_for_learning

    online_observations = 0
    for item in variant_results:
        record = item.get("_learning_record") or {
            "run_id": run_paths.run_id,
            "jd_hash": blueprint.jd_hash,
            "variant_id": item["variant_id"],
            "passed": item.get("passed", False),
            "status": item.get("status"),
        }
        record["attempt_no"] = item.get("attempt_no", 1)
        record["is_final_selection"] = True
        record["superseded"] = False  # final settled selection wins
        record["passed"] = bool(item.get("passed"))
        # Clear deferred-ineligible marker before computing eligibility.
        record.pop("eligible_for_learning", None)
        record["eligible_for_learning"] = is_record_eligible_for_learning(record)
        item["is_final_selection"] = True
        item["superseded"] = False
        item["_learning_record"] = record
        save_learning_outcome(record)
        # Phase 2.8: observe River only after finalization + eligibility.
        with contextlib.suppress(Exception):
            from resume_engine.learning.online.shadow_runner import observe_final_outcome

            obs = observe_final_outcome(blueprint=blueprint, learning_record=record)
            if obs is not None:
                online_observations += 1
        if item.get("passed") and item.get("_resume_object") is not None:
            save_fingerprint(
                jd_hash=blueprint.jd_hash,
                run_id=run_paths.run_id,
                variant_id=item["variant_id"],
                resume=item["_resume_object"],
                passed=True,
            )
        if not item.get("passed"):
            save_failure_record(record)

    final_resumes = []
    for item in variant_results:
        item.pop("_resume_object", None)
        item.pop("_variant_object", None)
        item.pop("_learning_record", None)
        if not item.get("final_resume"):
            continue
        resume_file = Path(item["final_resume"])
        if not resume_file.is_absolute():
            resume_file = PROJECT_ROOT / resume_file
        if not resume_file.exists():
            continue
        with open(resume_file, "r", encoding="utf-8") as f:
            final_resumes.append(ResumeJSON.model_validate(json.load(f)))
    progress("diversity", "Checking cross-variant similarity.", {"variant_count": len(final_resumes)})
    variant_similarity_result = (
        validate_variant_similarity(
            final_resumes,
            threshold=thresholds.VARIANT_SIMILARITY_MAX,
        )
        if len(final_resumes) > 1
        else None
    )

    learning_update = update_learning_patterns()

    exports: list[dict] = []
    if export_formats:
        progress("export", f"Exporting final resumes to {', '.join(export_formats).upper()}.", None)
        from resume_engine.export.service import export_resume

        contact = None
        if candidate_profile_path:
            contact = candidate_profile_path
        for item in variant_results:
            if not item.get("passed") or not item.get("final_resume"):
                continue
            resume_file = Path(item["final_resume"])
            if not resume_file.is_absolute():
                resume_file = PROJECT_ROOT / resume_file
            if not resume_file.exists():
                continue
            export_result = export_resume(
                resume_file,
                formats=export_formats,
                output_dir=run_paths.root / "exports",
                basename=f"{item['variant_id']}_final",
                contact=contact,
            )
            item["exports"] = export_result.get("artifacts")
            exports.append(
                {
                    "variant_id": item["variant_id"],
                    "artifacts": export_result.get("artifacts"),
                }
            )
    progress("finalize", "Saving run summary and final artifacts.", {"exports": len(exports)})

    result = {
        "phase": "Phase 2",
        "run_id": run_paths.run_id,
        "jd_hash": blueprint.jd_hash,
        "generation_mode": generation_context["generation_mode"],
        "blueprint": portable_path(blueprint_path),
        "resume_seed": portable_path(resume_seed_path) if resume_seed_path else None,
        "candidate_profile": portable_path(candidate_profile_path) if candidate_profile_path else None,
        "strategy": relative(strategy_path),
        "run_root": relative(run_paths.root),
        "variants_processed": len(variant_results),
        "variant_results": variant_results,
        "variant_diversity": variant_similarity_result.model_dump() if variant_similarity_result else None,
        "variant_regeneration": {
            "events": regen_events,
            "max_retries": thresholds.VARIANT_REGEN_MAX,
            "counts": regen_counts,
        },
        "exports": exports,
        "learning_update": {
            "updated": learning_update.get("updated"),
            "strategy_memory_summary": learning_update.get("strategy_memory_summary"),
            "outcome_count": learning_update.get("outcome_count"),
            "eligible_count": learning_update.get("eligible_count"),
            "learning_min_sample_count": learning_update.get("learning_min_sample_count"),
            "retrieval_applied": learning_insights.get("applied"),
            "retrieval_eligible_sample_count": learning_insights.get("eligible_sample_count"),
        },
        "online_learning": {
            "mode": "shadow",
            "policy_version": "river-linucb-v1",
            "shadow_decisions_recorded": online_shadow_decisions,
            "observations_recorded": online_observations,
            "fallbacks": online_fallbacks,
        },
    }

    if variant_similarity_result is not None:
        save_learning_outcome(
            {
                "record_type": "variant_diversity",
                "run_id": run_paths.run_id,
                "jd_hash": blueprint.jd_hash,
                "job_family": blueprint.job.primary_family,
                "primary_family": blueprint.job.primary_family,
                "secondary_family": blueprint.job.secondary_family,
                "hybrid_status": blueprint.job.hybrid_probability >= 0.55
                and blueprint.job.secondary_family != "none",
                "variant_strategy": "all_variants",
                "variant_diversity_result": variant_similarity_result.model_dump(),
                "variant_regeneration": regen_events,
            }
        )

    summary_path = run_paths.root / "phase2_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    result["summary_path"] = relative(summary_path)
    return result
