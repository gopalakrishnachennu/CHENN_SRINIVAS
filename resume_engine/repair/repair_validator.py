from resume_engine.config import thresholds
from resume_engine.models.validation_schema import ValidationBundle
from resume_engine.repair.repair_planner import build_repair_plan


def should_repair(bundle: ValidationBundle) -> bool:
    if bundle.optimization_score >= thresholds.PASS_SCORE_MIN and bundle.passed:
        return False
    return bundle.optimization_score >= thresholds.REPAIR_SCORE_MIN or not bundle.passed


def attach_repair_plan(bundle: ValidationBundle) -> ValidationBundle:
    bundle.repair_plan = build_repair_plan(bundle)
    if bundle.passed and bundle.optimization_score >= thresholds.PASS_SCORE_MIN:
        bundle.action = "PASS"
    elif should_repair(bundle):
        bundle.action = "REPAIR_REQUIRED"
    else:
        bundle.action = "FAIL_REGENERATE_OR_REVIEW"
    return bundle
