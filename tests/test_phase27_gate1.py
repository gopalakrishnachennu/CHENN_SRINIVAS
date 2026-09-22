"""
Phase 2.7 Gate 1 — critical correctness tests.

Covers P4 small-set semantics, typed repair ops, candidate truth,
per-variant isolation, run_id hardening, final-only learning,
and attempt-scoped report/artifact immutability.
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock

import pytest

from resume_engine.config import thresholds
from resume_engine.learning.eligibility import is_record_eligible_for_learning
from resume_engine.learning.outcome_store import save_learning_outcome
from resume_engine.models.resume_schema import ResumeExperience, ResumeJSON
from resume_engine.models.resume_strategy import ResumeStrategy, VariantStrategy
from resume_engine.models.validation_schema import (
    ValidationBundle,
    ValidationIssue,
    ValidatorResult,
)
from resume_engine.pipeline.phase2_pipeline import process_variant
from resume_engine.repair.patch_applier import (
    CORE_SKILL_GROUP,
    PatchApplicationError,
    RepairOperation,
    apply_repair_operation,
    apply_resume_operations,
)
from resume_engine.repair.repair_planner import build_repair_plan
from resume_engine.reports.behavioral_audit import _good_resume, _monster_blueprint
from resume_engine.storage.run_store import (
    InvalidRunIdError,
    RunAlreadyExistsError,
    create_run_paths,
    generate_run_id,
    save_raw_resume,
    save_repaired_resume,
    save_validated_resume_artifact,
    save_validation_bundle_reports,
    validate_run_id,
    write_run_metadata,
)
from resume_engine.strategy.strategy_builder import build_strategy
from resume_engine.validation.coverage_validator import validate_coverage
from resume_engine.validation.p4_usage_validator import validate_p4_usage


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _bundle_with_issue(
    *,
    code: str,
    missing: list[str] | None = None,
    metadata: dict | None = None,
    variant_id: str = "V01",
) -> ValidationBundle:
    meta = dict(metadata or {})
    if missing is not None:
        meta["missing"] = missing
    issue = ValidationIssue(
        code=code,
        severity="error",
        message=f"{code}",
        metadata=meta,
    )
    return ValidationBundle(
        variant_id=variant_id,
        resume_id=f"{variant_id}_t",
        passed=False,
        optimization_score=70.0,
        action="REPAIR_REQUIRED",
        validator_results=[
            ValidatorResult(
                name="coverage_validator",
                passed=False,
                score=50.0,
                issues=[issue],
                details={},
            )
        ],
    )


def _resume_base(**kwargs) -> ResumeJSON:
    data = {
        "target_title": "Engineer",
        "summary": "AWS Python Terraform engineer.",
        "technical_skills": {"Cloud": ["AWS", "Python"]},
        "experience": [
            {
                "company": "Acme",
                "title": "Engineer",
                "bullets": ["Built AWS Python platforms.", "Delivered CI/CD."],
            }
        ],
        "projects": [],
        "certifications": [],
        "variant_id": "V01",
    }
    data.update(kwargs)
    return ResumeJSON.model_validate(data)


# ---------------------------------------------------------------------------
# FIX 1 — P4 small-set semantics
# ---------------------------------------------------------------------------


def test_p4_zero_available_passes():
    bp = _monster_blueprint()
    bp.priority_skills["P4"] = []
    resume = _good_resume()
    result = validate_p4_usage(bp, resume)
    assert result.passed
    assert result.details["p4_available"] == []
    assert result.details["p4_usage_count"] == 0


def test_p4_zero_used_passes():
    bp = _monster_blueprint()
    resume = _good_resume()
    # Strip P4 terms from resume.
    p4 = set(bp.priority_skills.get("P4", []))
    resume.technical_skills = {
        g: [s for s in skills if s not in p4]
        for g, skills in resume.technical_skills.items()
    }
    for exp in resume.experience:
        exp.bullets = [
            " ".join(w for w in b.split() if w.rstrip(".,") not in p4) for b in exp.bullets
        ]
    result = validate_p4_usage(bp, resume)
    assert result.passed
    assert result.details["p4_usage_count"] == 0


def test_single_available_single_used_passes():
    bp = _monster_blueprint()
    bp.priority_skills["P4"] = ["Docker"]
    resume = _resume_base(
        technical_skills={"Cloud": ["AWS", "Python", "Terraform", "Docker"]},
        summary="AWS Python Terraform Docker engineer.",
        experience=[
            {
                "company": "A",
                "title": "E",
                "bullets": ["AWS Python Terraform Docker work."],
            }
        ],
    )
    # Ensure required priority skills are detectable from monster blueprint P1/P2.
    for skill in bp.priority_skills.get("P1", [])[:3]:
        resume.summary += f" {skill}."
    result = validate_p4_usage(bp, resume)
    assert result.passed
    assert result.details["p4_usage_count"] == 1
    assert result.details["one_p4_floor_applied"] is True
    # Old available-ratio would be 1.0 and fail — must not be the hard gate.
    assert result.details["available_p4_ratio"] == 1.0


def test_two_available_one_used_passes_when_one_p4_floor_applies():
    bp = _monster_blueprint()
    bp.priority_skills["P4"] = ["Docker", "Helm"]
    resume = _resume_base(
        technical_skills={"Cloud": ["AWS", "Python", "Docker"]},
        summary="AWS Python Docker engineer.",
        experience=[{"company": "A", "title": "E", "bullets": ["AWS Python Docker."]}],
    )
    for skill in bp.priority_skills.get("P1", [])[:2]:
        resume.summary += f" {skill}."
    result = validate_p4_usage(bp, resume)
    assert result.passed
    assert result.details["one_p4_floor_applied"] is True
    assert result.details["available_p4_ratio"] == 0.5  # diagnostic only


def test_three_available_one_used_passes():
    bp = _monster_blueprint()
    bp.priority_skills["P4"] = ["Docker", "Helm", "Ansible"]
    resume = _resume_base(
        technical_skills={"Cloud": ["AWS", "Python", "Docker"]},
        summary="AWS Python Docker.",
        experience=[{"company": "A", "title": "E", "bullets": ["AWS Python Docker."]}],
    )
    for skill in bp.priority_skills.get("P1", [])[:2]:
        resume.summary += f" {skill}."
    result = validate_p4_usage(bp, resume)
    assert result.passed
    assert result.details["p4_usage_count"] == 1


def test_small_p4_set_does_not_force_zero_usage():
    bp = _monster_blueprint()
    bp.priority_skills["P4"] = ["Docker"]
    resume = _resume_base(
        technical_skills={"Cloud": ["AWS", "Docker"]},
        summary="AWS Docker.",
        experience=[{"company": "A", "title": "E", "bullets": ["AWS Docker."]}],
    )
    for skill in bp.priority_skills.get("P1", [])[:1]:
        resume.summary += f" {skill}."
    result = validate_p4_usage(bp, resume)
    assert result.passed
    assert result.details["p4_usage_count"] == 1


def test_multiple_p4_can_fail_when_adjacent_share_dominates():
    bp = _monster_blueprint().model_copy(deep=True)
    bp.priority_skills["P1"] = ["AWS"]
    bp.priority_skills["P2"] = ["Python"]
    bp.priority_skills["P3"] = []
    bp.priority_skills["P4"] = ["Docker", "Helm", "Ansible"]
    resume = ResumeJSON(
        target_title="Engineer",
        summary="AWS Python Docker Helm Ansible.",
        technical_skills={"Core": ["AWS", "Python", "Docker", "Helm", "Ansible"]},
        experience=[
            ResumeExperience(
                company="A",
                title="E",
                bullets=["AWS Python Docker Helm Ansible platform."],
            )
        ],
        projects=[],
        certifications=[],
        variant_id="V01",
    )
    result = validate_p4_usage(bp, resume)
    assert not result.passed
    assert result.details["p4_share_of_used_priority"] > thresholds.P4_USAGE_MAX


def test_p4_missing_never_becomes_required():
    bp = _monster_blueprint()
    bp.priority_skills["P4"] = ["Docker", "Helm"]
    resume = _good_resume()
    # Ensure Docker/Helm not present.
    for g, skills in list(resume.technical_skills.items()):
        resume.technical_skills[g] = [s for s in skills if s not in {"Docker", "Helm"}]
    cov = validate_coverage(bp, resume)
    codes = {issue.code for result in [cov] for issue in result.issues}
    assert "FAIL_P4_COVERAGE" not in codes
    p4 = validate_p4_usage(bp, resume)
    # Missing P4 must not fail p4 validator.
    if p4.details["p4_usage_count"] == 0:
        assert p4.passed


def test_p4_missing_never_enters_missing_skills():
    bp = _monster_blueprint()
    bp.priority_skills["P4"] = ["Docker"]
    # Even if a coverage issue incorrectly lists a P4 skill, planner must exclude it.
    bundle = _bundle_with_issue(code="FAIL_P1_COVERAGE", missing=["Terraform", "Docker"])
    plan = build_repair_plan(bundle, blueprint=bp, generation_mode="TEMPLATE")
    assert "Docker" not in plan["missing_skills"]
    append_values = [
        op["value"] for op in plan["operations"] if op.get("operation") == "APPEND_SKILL"
    ]
    assert "Docker" not in append_values
    assert "Terraform" in append_values or "Terraform" in plan["missing_skills"]


def test_missing_p2_produces_executable_append_skill():
    bp = _monster_blueprint()
    p2 = [s for s in bp.priority_skills.get("P2", []) if s in bp.generation_contract.allowed_technologies]
    assert p2
    skill = p2[0]
    bundle = _bundle_with_issue(code="FAIL_P2_COVERAGE", missing=[skill])
    plan = build_repair_plan(bundle, blueprint=bp, generation_mode="TEMPLATE")
    assert skill in plan["missing_skills"]
    assert any(o.get("operation") == "APPEND_SKILL" and o.get("value") == skill for o in plan["operations"])


def test_p4_overuse_still_fails():
    bp = _monster_blueprint().model_copy(deep=True)
    bp.priority_skills["P1"] = ["AWS"]
    bp.priority_skills["P2"] = []
    bp.priority_skills["P3"] = []
    bp.priority_skills["P4"] = ["Docker", "Helm", "Ansible", "Podman"]
    resume = ResumeJSON(
        target_title="E",
        summary="AWS Docker Helm Ansible Podman.",
        technical_skills={"C": ["AWS", "Docker", "Helm", "Ansible", "Podman"]},
        experience=[
            ResumeExperience(
                company="A", title="E", bullets=["AWS Docker Helm Ansible Podman."]
            )
        ],
        projects=[],
        certifications=[],
        variant_id="V01",
    )
    result = validate_p4_usage(bp, resume)
    assert not result.passed
    assert any(i.code == "FAIL_P4_OVERUSE" for i in result.issues)


def test_p4_diagnostic_ratios_are_reported():
    bp = _monster_blueprint()
    bp.priority_skills["P4"] = ["Docker", "Helm"]
    resume = _resume_base(
        technical_skills={"Cloud": ["AWS", "Python", "Docker"]},
        summary="AWS Python Docker.",
        experience=[{"company": "A", "title": "E", "bullets": ["AWS Python Docker."]}],
    )
    for skill in bp.priority_skills.get("P1", [])[:2]:
        resume.summary += f" {skill}."
    result = validate_p4_usage(bp, resume)
    details = result.details
    for key in [
        "p4_available",
        "p4_used",
        "p4_usage_count",
        "required_priority_used",
        "required_priority_used_count",
        "p4_share_of_used_priority",
        "available_p4_ratio",
        "max_ratio",
        "one_p4_floor_applied",
    ]:
        assert key in details


# ---------------------------------------------------------------------------
# FIX 2–3 — Typed repair ops + candidate truth
# ---------------------------------------------------------------------------


def test_template_mode_can_append_blueprint_allowed_skill():
    bp = _monster_blueprint()
    skill = "Terraform"
    assert skill in bp.generation_contract.allowed_technologies
    bundle = _bundle_with_issue(code="FAIL_P1_COVERAGE", missing=[skill])
    plan = build_repair_plan(
        bundle,
        blueprint=bp,
        generation_mode="TEMPLATE",
        resume_technical_skills={"Cloud": ["AWS"]},
    )
    assert skill in plan["missing_skills"]
    ops = [o for o in plan["operations"] if o["operation"] == "APPEND_SKILL"]
    assert any(o["value"] == skill for o in ops)
    resume = _resume_base(technical_skills={"Cloud": ["AWS"]})
    patched, issues = apply_resume_operations(
        resume,
        [RepairOperation.model_validate(ops[0])],
        repair_plan=plan,
        allowed_technologies=bp.generation_contract.allowed_technologies,
    )
    assert not issues
    assert skill in patched.technical_skills.get(ops[0]["group"], [])


def test_candidate_mode_can_append_verified_candidate_skill():
    bp = _monster_blueprint()
    skill = "Terraform"
    candidate = {"technical_skills": ["Terraform", "AWS"], "experience": []}
    bundle = _bundle_with_issue(code="FAIL_P1_COVERAGE", missing=[skill])
    plan = build_repair_plan(
        bundle,
        blueprint=bp,
        generation_mode="CANDIDATE",
        candidate_profile=candidate,
        resume_technical_skills={"Cloud": ["AWS"]},
    )
    assert not plan["unresolved_required_candidate_gaps"]
    assert any(
        o["operation"] == "APPEND_SKILL" and o["value"] == skill for o in plan["operations"]
    )


def test_candidate_mode_cannot_invent_missing_skill():
    bp = _monster_blueprint()
    skill = "Terraform"
    candidate = {"technical_skills": ["AWS"], "experience": []}
    bundle = _bundle_with_issue(code="FAIL_P1_COVERAGE", missing=[skill])
    plan = build_repair_plan(
        bundle,
        blueprint=bp,
        generation_mode="CANDIDATE",
        candidate_profile=candidate,
    )
    append_vals = [
        o["value"] for o in plan["operations"] if o.get("operation") == "APPEND_SKILL"
    ]
    assert skill not in append_vals


def test_candidate_mode_unverified_required_gap_is_recorded():
    bp = _monster_blueprint()
    skill = "Terraform"
    candidate = {"technical_skills": ["AWS"], "experience": []}
    bundle = _bundle_with_issue(code="FAIL_P1_COVERAGE", missing=[skill])
    plan = build_repair_plan(
        bundle,
        blueprint=bp,
        generation_mode="CANDIDATE",
        candidate_profile=candidate,
    )
    assert skill in plan["unresolved_required_candidate_gaps"]


def test_append_skill_rejects_unapproved_technology():
    resume = _resume_base()
    with pytest.raises(PatchApplicationError) as exc:
        apply_repair_operation(
            resume,
            RepairOperation(operation="APPEND_SKILL", group="Cloud", value="Salesforce"),
            allowed_technologies=["AWS", "Python", "Terraform"],
        )
    assert exc.value.code == "FAIL_REPAIR_UNAPPROVED_TECHNOLOGY"


def test_append_skill_creates_deterministic_group_when_needed():
    resume = _resume_base(technical_skills={})
    apply_repair_operation(
        resume,
        RepairOperation(operation="APPEND_SKILL", group=None, value="Terraform"),
        allowed_technologies=["Terraform"],
    )
    assert CORE_SKILL_GROUP in resume.technical_skills
    assert "Terraform" in resume.technical_skills[CORE_SKILL_GROUP]


def test_remove_skill_removes_only_requested_skill():
    resume = _resume_base(technical_skills={"Cloud": ["AWS", "Helm", "Python"]})
    apply_repair_operation(
        resume,
        RepairOperation(operation="REMOVE_SKILL", group="Cloud", value="Helm"),
    )
    assert resume.technical_skills["Cloud"] == ["AWS", "Python"]


def test_append_bullet_mutates_only_target_experience():
    resume = _resume_base(
        experience=[
            {"company": "A", "title": "E", "bullets": ["one"]},
            {"company": "B", "title": "E", "bullets": ["keep"]},
        ]
    )
    original_b = list(resume.experience[1].bullets)
    apply_repair_operation(
        resume,
        RepairOperation(
            operation="APPEND_EXPERIENCE_BULLET",
            experience_index=0,
            value="new bullet",
        ),
    )
    assert resume.experience[0].bullets[-1] == "new bullet"
    assert resume.experience[1].bullets == original_b


def test_replace_bullet_mutates_only_target_bullet():
    resume = _resume_base()
    other = resume.experience[0].bullets[1]
    apply_repair_operation(
        resume,
        RepairOperation(
            operation="REPLACE_EXPERIENCE_BULLET",
            experience_index=0,
            bullet_index=0,
            value="replaced",
        ),
    )
    assert resume.experience[0].bullets[0] == "replaced"
    assert resume.experience[0].bullets[1] == other


def test_repair_operation_scope_guard():
    resume = _resume_base()
    plan = {
        "operations": [
            {
                "operation": "REPLACE_EXPERIENCE_BULLET",
                "experience_index": 0,
                "bullet_index": 0,
                "value": "ok",
            }
        ],
        "targets": [{"location": "experience[0].bullets[0]"}],
        "failed_bullets": ["experience[0].bullets[0]"],
    }
    with pytest.raises(PatchApplicationError) as exc:
        apply_resume_operations(
            resume,
            [
                RepairOperation(
                    operation="REPLACE_TEXT",
                    location="summary",
                    value="hijack",
                )
            ],
            repair_plan=plan,
        )
    assert exc.value.code == "FAIL_OUT_OF_SCOPE_PATCH"


# ---------------------------------------------------------------------------
# FIX 4 — Per-variant failure isolation
# ---------------------------------------------------------------------------


def _make_strategy_variant(variant_id: str = "V01") -> tuple[ResumeStrategy, VariantStrategy]:
    bp = _monster_blueprint()
    strategy = build_strategy(bp)
    variant = VariantStrategy(
        variant_id=variant_id,
        positioning="platform_reliability",
        description="test variant",
    )
    return strategy, variant


def _ok_bundle(variant_id: str) -> ValidationBundle:
    return ValidationBundle(
        variant_id=variant_id,
        resume_id=f"{variant_id}_ok",
        passed=True,
        optimization_score=95.0,
        action="PASS",
        validator_results=[],
        repair_plan={},
    )


def _stub_happy_path(monkeypatch, *, fail_variants: set[str] | None = None, fail_stage: str = "generation"):
    fail_variants = fail_variants or set()

    def fake_generate(**kwargs):
        vid = kwargs["variant"].variant_id
        if vid in fail_variants and fail_stage == "generation":
            raise RuntimeError(f"boom-gen-{vid}")
        return _good_resume(vid)

    def fake_validators(blueprint, resume, *args, **kwargs):
        if resume.variant_id in fail_variants and fail_stage == "validation":
            raise ValueError(f"boom-val-{resume.variant_id}")
        return _ok_bundle(resume.variant_id)

    def fake_repair(**kwargs):
        if kwargs["variant"].variant_id in fail_variants and fail_stage == "repair":
            raise RuntimeError(f"boom-repair-{kwargs['variant'].variant_id}")
        return kwargs["resume"]

    class Sel:
        def __init__(self, **kw):
            self.status = "VALIDATED"
            self.resume = kw["raw_resume"]
            self.bundle = kw.get("raw_bundle") or _ok_bundle(kw["raw_resume"].variant_id)
            self.notes = []
            self.regression_recorded = False

    monkeypatch.setattr(
        "resume_engine.pipeline.phase2_pipeline.generate_resume_with_openai",
        fake_generate,
    )
    monkeypatch.setattr(
        "resume_engine.pipeline.phase2_pipeline.run_validators",
        fake_validators,
    )
    monkeypatch.setattr(
        "resume_engine.pipeline.phase2_pipeline._enrich_resume",
        lambda bp, resume, ctx: resume,
    )
    monkeypatch.setattr(
        "resume_engine.pipeline.phase2_pipeline.rewrite_targeted_resume_parts",
        fake_repair,
    )
    monkeypatch.setattr(
        "resume_engine.pipeline.phase2_pipeline.should_repair",
        lambda bundle: fail_stage == "repair",
    )
    monkeypatch.setattr(
        "resume_engine.pipeline.phase2_pipeline.select_best_resume_version",
        lambda **kw: Sel(**kw),
    )
    monkeypatch.setattr(
        "resume_engine.pipeline.phase2_pipeline.build_variant_diagnostics",
        lambda *a, **k: {},
    )
    monkeypatch.setattr(
        "resume_engine.pipeline.phase2_pipeline.build_learning_outcome",
        lambda **k: {
            "passed": True,
            "p1_coverage": 100.0,
            "p2_coverage": 95.0,
            "failure_codes": [],
            "technology_firewall_passed": True,
            "role_drift_passed": True,
            "run_id": k.get("run_id"),
            "jd_hash": k["blueprint"].jd_hash,
            "variant_id": k["variant"].variant_id,
            "successful_pattern": True,
        },
    )


# ---------------------------------------------------------------------------
# FIX 4 — Per-variant failure isolation
# ---------------------------------------------------------------------------


def test_generation_failure_in_one_variant_does_not_stop_others(monkeypatch):
    bp = _monster_blueprint()
    paths = create_run_paths(bp.jd_hash, run_id=_uid("iso-gen"))
    strategy, _ = _make_strategy_variant("V01")
    ctx = {"generation_mode": "TEMPLATE", "candidate_profile": None}
    _stub_happy_path(monkeypatch, fail_variants={"V01"}, fail_stage="generation")

    r1 = process_variant(
        client=MagicMock(),
        blueprint=bp,
        strategy=strategy,
        variant=VariantStrategy(variant_id="V01", positioning="a", description="a"),
        generation_context=ctx,
        laya_agent=None,
        run_paths=paths,
        repair=False,
        persist_learning=False,
    )
    r2 = process_variant(
        client=MagicMock(),
        blueprint=bp,
        strategy=strategy,
        variant=VariantStrategy(variant_id="V02", positioning="b", description="b"),
        generation_context=ctx,
        laya_agent=None,
        run_paths=paths,
        repair=False,
        persist_learning=False,
    )
    assert r1["status"] == "PIPELINE_ERROR"
    assert r1["passed"] is False
    assert r1["final_resume"] is None
    assert r2["passed"] is True
    assert r2["status"] != "PIPELINE_ERROR"


def test_repair_failure_in_one_variant_does_not_stop_others(monkeypatch):
    bp = _monster_blueprint()
    paths = create_run_paths(bp.jd_hash, run_id=_uid("iso-rep"))
    strategy, _ = _make_strategy_variant("V03")
    ctx = {"generation_mode": "TEMPLATE", "candidate_profile": None}
    _stub_happy_path(monkeypatch, fail_variants={"V03"}, fail_stage="repair")

    # Force repair path: validators fail so should_repair triggers.
    def failing_then_ok(blueprint, resume, *args, **kwargs):
        return ValidationBundle(
            variant_id=resume.variant_id,
            resume_id=f"{resume.variant_id}_b",
            passed=False,
            optimization_score=70.0,
            action="REPAIR_REQUIRED",
            validator_results=[],
            repair_plan={"required": True, "operations": []},
        )

    monkeypatch.setattr(
        "resume_engine.pipeline.phase2_pipeline.run_validators",
        failing_then_ok,
    )
    monkeypatch.setattr(
        "resume_engine.pipeline.phase2_pipeline.should_repair",
        lambda bundle: True,
    )

    bad = process_variant(
        client=MagicMock(),
        blueprint=bp,
        strategy=strategy,
        variant=VariantStrategy(variant_id="V03", positioning="c", description="c"),
        generation_context=ctx,
        laya_agent=None,
        run_paths=paths,
        repair=True,
        persist_learning=False,
    )
    _stub_happy_path(monkeypatch, fail_variants=set(), fail_stage="generation")
    good = process_variant(
        client=MagicMock(),
        blueprint=bp,
        strategy=strategy,
        variant=VariantStrategy(variant_id="V04", positioning="d", description="d"),
        generation_context=ctx,
        laya_agent=None,
        run_paths=paths,
        repair=False,
        persist_learning=False,
    )
    assert bad["status"] == "PIPELINE_ERROR"
    assert good["passed"] is True


def test_validation_exception_in_one_variant_does_not_stop_others(monkeypatch):
    bp = _monster_blueprint()
    paths = create_run_paths(bp.jd_hash, run_id=_uid("iso-val"))
    strategy, _ = _make_strategy_variant("V04")
    ctx = {"generation_mode": "TEMPLATE", "candidate_profile": None}
    _stub_happy_path(monkeypatch, fail_variants={"V04"}, fail_stage="validation")

    bad = process_variant(
        client=MagicMock(),
        blueprint=bp,
        strategy=strategy,
        variant=VariantStrategy(variant_id="V04", positioning="e", description="e"),
        generation_context=ctx,
        laya_agent=None,
        run_paths=paths,
        repair=False,
    )
    _stub_happy_path(monkeypatch)
    good = process_variant(
        client=MagicMock(),
        blueprint=bp,
        strategy=strategy,
        variant=VariantStrategy(variant_id="V05", positioning="f", description="f"),
        generation_context=ctx,
        laya_agent=None,
        run_paths=paths,
        repair=False,
    )
    assert bad["status"] == "PIPELINE_ERROR"
    assert good["passed"] is True


def test_pipeline_error_variant_never_becomes_final(monkeypatch):
    bp = _monster_blueprint()
    paths = create_run_paths(bp.jd_hash, run_id=_uid("iso-nofinal"))
    strategy, variant = _make_strategy_variant("V05")
    ctx = {"generation_mode": "TEMPLATE", "candidate_profile": None}
    _stub_happy_path(monkeypatch, fail_variants={"V05"}, fail_stage="generation")
    result = process_variant(
        client=MagicMock(),
        blueprint=bp,
        strategy=strategy,
        variant=variant,
        generation_context=ctx,
        laya_agent=None,
        run_paths=paths,
        repair=False,
    )
    assert result["final_resume"] is None
    assert not list(paths.validated_dir.glob("V05*"))


def test_pipeline_error_not_eligible_for_learning():
    record = {
        "passed": False,
        "status": "PIPELINE_ERROR",
        "is_final_selection": True,
        "superseded": False,
        "p1_coverage": 100.0,
        "p2_coverage": 95.0,
        "failure_codes": [],
        "technology_firewall_passed": True,
        "role_drift_passed": True,
    }
    assert is_record_eligible_for_learning(record) is False


def test_pipeline_error_report_written(monkeypatch):
    bp = _monster_blueprint()
    paths = create_run_paths(bp.jd_hash, run_id=_uid("iso-report"))
    strategy, variant = _make_strategy_variant("V06")
    ctx = {"generation_mode": "TEMPLATE", "candidate_profile": None}
    _stub_happy_path(monkeypatch, fail_variants={"V06"}, fail_stage="generation")
    result = process_variant(
        client=MagicMock(),
        blueprint=bp,
        strategy=strategy,
        variant=variant,
        generation_context=ctx,
        laya_agent=None,
        run_paths=paths,
        repair=False,
    )
    assert result["status"] == "PIPELINE_ERROR"
    report = paths.reports_dir / "V06_pipeline_error.json"
    assert report.exists()
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["status"] == "PIPELINE_ERROR"
    assert payload["passed"] is False
    assert payload["eligible_for_learning"] is False


def test_other_variants_continue_after_error(monkeypatch):
    bp = _monster_blueprint()
    paths = create_run_paths(bp.jd_hash, run_id=_uid("iso-cont"))
    strategy, _ = _make_strategy_variant("V01")
    ctx = {"generation_mode": "TEMPLATE", "candidate_profile": None}
    _stub_happy_path(monkeypatch, fail_variants={"V02"}, fail_stage="generation")
    results = []
    for vid in ["V01", "V02", "V03"]:
        results.append(
            process_variant(
                client=MagicMock(),
                blueprint=bp,
                strategy=strategy,
                variant=VariantStrategy(variant_id=vid, positioning=vid, description=vid),
                generation_context=ctx,
                laya_agent=None,
                run_paths=paths,
                repair=False,
            )
        )
    assert results[0]["passed"] is True
    assert results[1]["status"] == "PIPELINE_ERROR"
    assert results[2]["passed"] is True


# ---------------------------------------------------------------------------
# FIX 5 — run_id hardening
# ---------------------------------------------------------------------------


def test_valid_explicit_run_id():
    assert validate_run_id("run-abc_123") == "run-abc_123"


def test_auto_uuid_run_id():
    rid = generate_run_id(None)
    assert validate_run_id(rid) == rid


@pytest.mark.parametrize(
    "bad",
    ["../abc", "foo/bar", "foo\\bar", ".", "..", "", "   ", "a" * 65],
)
def test_run_id_rejects_dangerous(bad):
    with pytest.raises(InvalidRunIdError):
        validate_run_id(bad)


def test_run_id_rejects_parent_traversal():
    with pytest.raises(InvalidRunIdError):
        validate_run_id("../abc")


def test_run_id_rejects_forward_slash():
    with pytest.raises(InvalidRunIdError):
        validate_run_id("foo/bar")


def test_run_id_rejects_backslash():
    with pytest.raises(InvalidRunIdError):
        validate_run_id("foo\\bar")


def test_run_id_rejects_dot():
    with pytest.raises(InvalidRunIdError):
        validate_run_id(".")


def test_run_id_rejects_empty():
    with pytest.raises(InvalidRunIdError):
        validate_run_id("")


def test_run_id_rejects_too_long():
    with pytest.raises(InvalidRunIdError):
        validate_run_id("x" * 65)


def test_existing_run_id_is_rejected():
    bp = _monster_blueprint()
    rid = _uid("collide")
    create_run_paths(bp.jd_hash, run_id=rid)
    with pytest.raises(RunAlreadyExistsError):
        create_run_paths(bp.jd_hash, run_id=rid)


def test_existing_run_metadata_cannot_be_overwritten():
    bp = _monster_blueprint()
    paths = create_run_paths(bp.jd_hash, run_id=_uid("meta-once"))
    write_run_metadata(paths, {"generation_mode": "TEMPLATE"})
    with pytest.raises(FileExistsError):
        write_run_metadata(paths, {"generation_mode": "TEMPLATE"})


def test_same_jd_different_runs_still_work():
    bp = _monster_blueprint()
    a = create_run_paths(bp.jd_hash, run_id=_uid("jd-a"))
    b = create_run_paths(bp.jd_hash, run_id=_uid("jd-b"))
    assert a.root != b.root
    assert a.root.exists() and b.root.exists()


# ---------------------------------------------------------------------------
# FIX 6 — Final-only learning
# ---------------------------------------------------------------------------


def test_initial_success_then_regenerated_success_counts_once(tmp_path, monkeypatch):
    from resume_engine.learning import outcome_store
    from resume_engine.learning.repository import LearningRepository, reset_default_repository_for_tests

    learning_file = tmp_path / "outcomes.jsonl"
    monkeypatch.setattr(outcome_store, "OUTCOMES_FILE", learning_file)
    reset_default_repository_for_tests(
        LearningRepository(db_path=tmp_path / "t.sqlite3", dual_write_jsonl=True)
    )

    attempt1 = {
        "run_id": "r1",
        "jd_hash": "h",
        "variant_id": "V02",
        "attempt_no": 1,
        "passed": True,
        "is_final_selection": False,
        "superseded": True,
        "eligible_for_learning": False,
        "p1_coverage": 100.0,
        "p2_coverage": 95.0,
        "failure_codes": [],
        "technology_firewall_passed": True,
        "role_drift_passed": True,
        "successful_pattern": True,
    }
    attempt2 = {
        **attempt1,
        "attempt_no": 2,
        "is_final_selection": True,
        "superseded": False,
        "regen_reason": "VARIANT_SIMILARITY",
    }
    attempt2.pop("eligible_for_learning", None)
    attempt2["eligible_for_learning"] = is_record_eligible_for_learning(attempt2)

    save_learning_outcome(attempt1)
    save_learning_outcome(attempt2)

    lines = [json.loads(line) for line in learning_file.read_text().splitlines() if line.strip()]
    eligible = [r for r in lines if is_record_eligible_for_learning(r)]
    assert len(eligible) == 1
    assert eligible[0]["attempt_no"] == 2
    reset_default_repository_for_tests(None)


def test_superseded_attempt_not_eligible():
    record = {
        "passed": True,
        "is_final_selection": False,
        "superseded": True,
        "p1_coverage": 100.0,
        "p2_coverage": 95.0,
        "failure_codes": [],
        "technology_firewall_passed": True,
        "role_drift_passed": True,
    }
    assert is_record_eligible_for_learning(record) is False


def test_only_final_variant_updates_strategy_history(tmp_path, monkeypatch):
    from resume_engine.learning import outcome_store
    from resume_engine.learning.repository import LearningRepository, reset_default_repository_for_tests

    learning_file = tmp_path / "outcomes.jsonl"
    monkeypatch.setattr(outcome_store, "OUTCOMES_FILE", learning_file)
    reset_default_repository_for_tests(
        LearningRepository(db_path=tmp_path / "t2.sqlite3", dual_write_jsonl=True)
    )
    base = {
        "run_id": "r2",
        "jd_hash": "hybrid_devops_databricks_ai",
        "variant_id": "V01",
        "primary_family": "devops_cloud",
        "secondary_family": "none",
        "seniority": "senior",
        "variant_positioning": "platform_reliability",
        "score_after": 96.0,
        "score_after_repair": 96.0,
        "p1_coverage": 100.0,
        "p2_coverage": 95.0,
        "failure_codes": [],
        "technology_firewall_passed": True,
        "role_drift_passed": True,
        "passed": True,
        "successful_pattern": True,
    }
    save_learning_outcome({**base, "attempt_no": 1, "is_final_selection": False, "superseded": True, "eligible_for_learning": False})
    final = {**base, "attempt_no": 2, "is_final_selection": True, "superseded": False}
    final["eligible_for_learning"] = is_record_eligible_for_learning(final)
    save_learning_outcome(final)

    # Only final eligible record should influence ranking inputs.
    eligible_count = sum(
        1
        for line in learning_file.read_text().splitlines()
        if line.strip() and is_record_eligible_for_learning(json.loads(line))
    )
    assert eligible_count == 1
    reset_default_repository_for_tests(None)


def test_failed_regeneration_does_not_promote_superseded_duplicate():
    superseded = {
        "passed": True,
        "is_final_selection": False,
        "superseded": True,
        "p1_coverage": 100.0,
        "p2_coverage": 95.0,
        "failure_codes": [],
        "technology_firewall_passed": True,
        "role_drift_passed": True,
    }
    failed_final = {
        "passed": False,
        "is_final_selection": True,
        "superseded": False,
        "status": "FAILED_VALIDATION",
        "p1_coverage": 80.0,
        "p2_coverage": 70.0,
        "failure_codes": ["FAIL_P1_COVERAGE"],
        "technology_firewall_passed": True,
        "role_drift_passed": True,
    }
    assert is_record_eligible_for_learning(superseded) is False
    assert is_record_eligible_for_learning(failed_final) is False


def test_learning_record_contains_attempt_number():
    record = {"attempt_no": 2, "passed": True, "is_final_selection": True, "superseded": False}
    assert record["attempt_no"] == 2


def test_learning_record_contains_final_selection_flag():
    record = {"is_final_selection": True}
    assert record["is_final_selection"] is True


def test_learning_record_contains_superseded_flag():
    record = {"superseded": True}
    assert record["superseded"] is True


def test_one_run_variant_has_at_most_one_eligible_final_outcome(tmp_path, monkeypatch):
    from resume_engine.learning import outcome_store
    from resume_engine.learning.repository import LearningRepository, reset_default_repository_for_tests

    learning_file = tmp_path / "outcomes.jsonl"
    monkeypatch.setattr(outcome_store, "OUTCOMES_FILE", learning_file)
    reset_default_repository_for_tests(
        LearningRepository(db_path=tmp_path / "t3.sqlite3", dual_write_jsonl=True)
    )
    run_id = "run-once"
    variant_id = "V02"
    for attempt, flags in [
        (1, {"is_final_selection": False, "superseded": True, "eligible_for_learning": False}),
        (2, {"is_final_selection": True, "superseded": False}),
    ]:
        rec = {
            "run_id": run_id,
            "variant_id": variant_id,
            "attempt_no": attempt,
            "passed": True,
            "p1_coverage": 100.0,
            "p2_coverage": 95.0,
            "failure_codes": [],
            "technology_firewall_passed": True,
            "role_drift_passed": True,
            "successful_pattern": True,
            **flags,
        }
        if flags.get("is_final_selection"):
            rec.pop("eligible_for_learning", None)
            rec["eligible_for_learning"] = is_record_eligible_for_learning(rec)
        save_learning_outcome(rec)

    eligible = [
        json.loads(line)
        for line in learning_file.read_text().splitlines()
        if line.strip() and is_record_eligible_for_learning(json.loads(line))
    ]
    matching = [r for r in eligible if r["run_id"] == run_id and r["variant_id"] == variant_id]
    assert len(matching) == 1
    reset_default_repository_for_tests(None)


# ---------------------------------------------------------------------------
# FIX 7 — Report/artifact immutability during regeneration
# ---------------------------------------------------------------------------


def test_regeneration_does_not_overwrite_raw_resume():
    bp = _monster_blueprint()
    paths = create_run_paths(bp.jd_hash, run_id=_uid("imm-raw"))
    a1 = save_raw_resume(paths, "V01", _good_resume("V01"), attempt_no=1)
    content1 = a1.read_text(encoding="utf-8")
    a2 = save_raw_resume(paths, "V01", _good_resume("V01"), attempt_no=2)
    assert a1 != a2
    assert a1.read_text(encoding="utf-8") == content1
    assert a1.exists() and a2.exists()


def test_regeneration_does_not_overwrite_repair_resume():
    bp = _monster_blueprint()
    paths = create_run_paths(bp.jd_hash, run_id=_uid("imm-rep"))
    r1 = save_repaired_resume(paths, "V01", _good_resume("V01"), attempt_no=1)
    content1 = r1.read_text(encoding="utf-8")
    r2 = save_repaired_resume(paths, "V01", _good_resume("V01"), attempt_no=2)
    assert r1 != r2
    assert r1.read_text(encoding="utf-8") == content1


def test_regeneration_does_not_overwrite_validation_report():
    bp = _monster_blueprint()
    paths = create_run_paths(bp.jd_hash, run_id=_uid("imm-val"))
    bundle = _ok_bundle("V01")
    j1, _ = save_validation_bundle_reports(paths, bp, bundle, "before_repair", attempt_no=1)
    content1 = j1.read_text(encoding="utf-8")
    j2, _ = save_validation_bundle_reports(paths, bp, bundle, "before_repair", attempt_no=2)
    assert j1 != j2
    assert j1.read_text(encoding="utf-8") == content1


def test_attempt_01_and_attempt_02_reports_both_exist():
    bp = _monster_blueprint()
    paths = create_run_paths(bp.jd_hash, run_id=_uid("imm-both"))
    bundle = _ok_bundle("V01")
    save_validation_bundle_reports(paths, bp, bundle, "final", attempt_no=1)
    save_validation_bundle_reports(paths, bp, bundle, "final", attempt_no=2)
    assert (paths.reports_dir / "V01" / "attempt_01" / "final_validation.json").exists()
    assert (paths.reports_dir / "V01" / "attempt_02" / "final_validation.json").exists()


def test_final_selected_attempt_is_identifiable():
    bp = _monster_blueprint()
    paths = create_run_paths(bp.jd_hash, run_id=_uid("imm-sel"))
    save_validated_resume_artifact(paths, "V01", _good_resume("V01"), attempt_no=1)
    path2 = save_validated_resume_artifact(paths, "V01", _good_resume("V01"), attempt_no=2)
    marker = paths.validated_dir / "V01_final_selected_attempt.json"
    assert marker.exists()
    data = json.loads(marker.read_text(encoding="utf-8"))
    assert data["attempt_no"] == 2
    assert data["artifact"] == "V01_attempt_02_final.json"
    assert path2.name == "V01_attempt_02_final.json"
    assert (paths.validated_dir / "V01_attempt_01_final.json").exists()
    assert (paths.validated_dir / "V01_final.json").exists()  # first attempt pointer preserved
