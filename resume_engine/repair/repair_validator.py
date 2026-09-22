from resume_engine.config import thresholds
from resume_engine.models.jd_blueprint import JDBlueprint
from resume_engine.models.resume_schema import ResumeJSON
from resume_engine.models.validation_schema import ValidationBundle
from resume_engine.repair.repair_planner import build_repair_plan


def should_repair(bundle: ValidationBundle) -> bool:
    if bundle.optimization_score >= thresholds.PASS_SCORE_MIN and bundle.passed:
        return False
    return bundle.optimization_score >= thresholds.REPAIR_SCORE_MIN or not bundle.passed


def attach_repair_plan(
    bundle: ValidationBundle,
    blueprint: JDBlueprint | None = None,
    *,
    generation_mode: str = "TEMPLATE",
    candidate_profile: dict | None = None,
    resume: ResumeJSON | None = None,
) -> ValidationBundle:
    bundle.repair_plan = build_repair_plan(
        bundle,
        blueprint=blueprint,
        generation_mode=generation_mode,
        candidate_profile=candidate_profile,
        resume_technical_skills=(resume.technical_skills if resume is not None else None),
    )
    # Candidate truth gaps on hard requirements prevent a clean pass path.
    if bundle.repair_plan.get("unresolved_required_candidate_gaps"):
        bundle.passed = False

    if bundle.passed and bundle.optimization_score >= thresholds.PASS_SCORE_MIN:
        bundle.action = "PASS"
    elif should_repair(bundle):
        bundle.action = "REPAIR_REQUIRED"
    else:
        bundle.action = "FAIL_REGENERATE_OR_REVIEW"
    return bundle
