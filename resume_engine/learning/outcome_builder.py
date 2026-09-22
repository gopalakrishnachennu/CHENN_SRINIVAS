"""Build richer learning outcome records for Wave 3 persistence."""

from __future__ import annotations

from typing import Any

from resume_engine.config.settings import PROMPT_VERSION
from resume_engine.learning.eligibility import (
    is_hybrid_blueprint,
    is_record_eligible_for_learning,
)
from resume_engine.models.jd_blueprint import JDBlueprint
from resume_engine.models.resume_strategy import VariantStrategy
from resume_engine.models.validation_schema import ValidationBundle


def _validator_passed(bundle: ValidationBundle, name: str) -> bool | None:
    for result in bundle.validator_results:
        if result.name == name:
            return bool(result.passed)
    return None


def _subscore(bundle: ValidationBundle, key: str) -> float | None:
    value = bundle.subscores.get(key)
    return float(value) if value is not None else None


def build_learning_outcome(
    *,
    blueprint: JDBlueprint,
    variant: VariantStrategy,
    run_id: str,
    strategy_id: str,
    before_bundle: ValidationBundle,
    selection_bundle: ValidationBundle,
    passed: bool,
    status: str,
    repaired: bool,
    regression_recorded: bool,
    selection_notes: list[str],
    diagnostics: dict[str, Any],
    model: str | None,
    prompt_version: str | None = None,
    variant_diversity: float | None = None,
) -> dict[str, Any]:
    failure_codes = [
        issue.code
        for result in selection_bundle.validator_results
        for issue in result.issues
    ]
    successful_repairs: list[str] = []
    if repaired and selection_bundle.passed and not before_bundle.passed:
        before_codes = {
            issue.code
            for result in before_bundle.validator_results
            for issue in result.issues
        }
        after_codes = set(failure_codes)
        successful_repairs = sorted(before_codes - after_codes)

    record: dict[str, Any] = {
        "run_id": run_id,
        "jd_hash": blueprint.jd_hash,
        "job_family": blueprint.job.primary_family,
        "primary_family": blueprint.job.primary_family,
        "secondary_family": blueprint.job.secondary_family,
        "hybrid": is_hybrid_blueprint(
            blueprint.job.secondary_family,
            blueprint.job.hybrid_probability,
        ),
        "hybrid_probability": blueprint.job.hybrid_probability,
        "seniority": blueprint.job.seniority,
        "strategy": strategy_id,
        "variant_id": variant.variant_id,
        "variant_positioning": variant.positioning,
        "p1_coverage": _subscore(selection_bundle, "p1_coverage"),
        "p2_coverage": _subscore(selection_bundle, "p2_coverage"),
        "responsibility_coverage": _subscore(selection_bundle, "responsibility_coverage"),
        "role_alignment": _subscore(selection_bundle, "role_alignment"),
        "technology_alignment": _subscore(selection_bundle, "technology_alignment"),
        "laya_alignment": _subscore(selection_bundle, "bullet_quality"),
        "duplicate_score": _subscore(selection_bundle, "duplicate_safety"),
        "p4_usage": _subscore(selection_bundle, "p4_usage"),
        "score_before": before_bundle.optimization_score,
        "score_after": selection_bundle.optimization_score,
        "score_before_repair": before_bundle.optimization_score,
        "score_after_repair": selection_bundle.optimization_score,
        "passed": passed,
        "successful_pattern": passed,
        "status": status,
        "repair_count": 1 if repaired else 0,
        "failure_codes": failure_codes,
        "failures": failure_codes,
        "successful_repairs": successful_repairs,
        "variant_diversity": variant_diversity,
        "prompt_version": prompt_version or PROMPT_VERSION,
        "model": model,
        "technology_firewall_passed": _validator_passed(
            selection_bundle, "technology_firewall"
        ),
        "role_drift_passed": _validator_passed(selection_bundle, "role_drift_validator"),
        "repair_score_regression": regression_recorded,
        "selection_notes": selection_notes,
        "variant_focus_score": diagnostics.get("variant_focus_score"),
        "JD_COMPATIBILITY_SCORE": selection_bundle.optimization_score,
        "repairs": before_bundle.repair_plan if repaired else {},
    }
    record["eligible_for_learning"] = is_record_eligible_for_learning(record)
    return record
