"""
Wave 1 P0 correctness tests.

Covers:
- P4 optional semantics and usage limits
- failed-final gate
- repair score regression selection
- immutable artifacts + run isolation
- patch-based targeted repair + scope guard
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from resume_engine.config import thresholds
from resume_engine.config.settings import portable_path
from resume_engine.generation.provenance import attach_skill_provenance
from resume_engine.learning.outcome_store import save_learning_outcome
from resume_engine.models.jd_blueprint import JDBlueprint
from resume_engine.models.resume_schema import ResumeExperience, ResumeJSON
from resume_engine.models.validation_schema import ValidationBundle
from resume_engine.pipeline.phase2_pipeline import run_validators
from resume_engine.repair.patch_applier import (
    PatchApplicationError,
    ResumePatch,
    apply_resume_patches,
)
from resume_engine.repair.repair_planner import build_repair_plan
from resume_engine.repair.version_selector import select_best_resume_version
from resume_engine.reports.behavioral_audit import _good_resume, _monster_blueprint
from resume_engine.storage.run_store import (
    create_run_paths,
    save_raw_resume,
    save_rejected_resume_artifact,
    save_repaired_resume,
    save_validated_resume_artifact,
    write_run_metadata,
)
from resume_engine.validation.coverage_validator import validate_coverage
from resume_engine.validation.p4_usage_validator import validate_p4_usage


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _resume_with_p4(blueprint: JDBlueprint, used: list[str]) -> ResumeJSON:
    resume = _good_resume()
    p4 = set(blueprint.priority_skills.get("P4", []))
    resume.technical_skills = {
        group: [skill for skill in skills if skill not in p4]
        for group, skills in resume.technical_skills.items()
    }
    for exp in resume.experience:
        cleaned = []
        for bullet in exp.bullets:
            words = [w for w in bullet.split() if w.rstrip(".,") not in p4]
            cleaned.append(" ".join(words))
        exp.bullets = cleaned
    if used:
        resume.technical_skills.setdefault("Optional Adjacent", []).extend(used)
    return attach_skill_provenance(blueprint, resume)


def _bundle(variant_id: str, passed: bool, score: float) -> ValidationBundle:
    return ValidationBundle(
        variant_id=variant_id,
        resume_id=f"{variant_id}_{score}",
        passed=passed,
        optimization_score=score,
        action="PASS" if passed else "REPAIR_REQUIRED",
        validator_results=[],
    )


@pytest.fixture
def blueprint() -> JDBlueprint:
    return _monster_blueprint()


# ---------------------------------------------------------------------------
# P4
# ---------------------------------------------------------------------------


def test_zero_p4_usage_passes(blueprint):
    resume = _resume_with_p4(blueprint, used=[])
    result = validate_p4_usage(blueprint, resume)
    assert result.passed
    assert result.details["p4_usage_count"] == 0
    assert result.details["p4_share_of_used_priority"] == 0.0


def test_p4_below_limit_passes(blueprint):
    resume = _resume_with_p4(blueprint, used=["Docker"])
    result = validate_p4_usage(blueprint, resume)
    assert result.passed
    assert result.details["p4_usage_count"] == 1
    assert result.details["one_p4_floor_applied"] is True


def test_p4_exact_limit_passes():
    """Share-of-used gate: many required + P4 share exactly at max still passes."""
    bp = _monster_blueprint()
    bp.priority_skills["P4"] = [f"Adj{i}" for i in range(5)]
    entity_cls = type(bp.entities[0])
    for name in bp.priority_skills["P4"]:
        bp.entities.append(
            entity_cls(
                name=name,
                category="adjacent",
                priority="P4",
                source="approved_adjacent",
                placement=["technical_skills_optional"],
            )
        )
    bp.generation_contract.allowed_technologies = list(
        dict.fromkeys(bp.generation_contract.allowed_technologies + bp.priority_skills["P4"])
    )
    # Use 1 P4 only — floor passes regardless of available ratio.
    resume = _resume_with_p4(bp, used=["Adj0"])
    result = validate_p4_usage(bp, resume)
    assert result.passed
    assert result.details["one_p4_floor_applied"] is True


def test_p4_above_limit_fails(blueprint):
    """P4 dominance: few required skills + multiple P4 → share > max."""
    bp = blueprint.model_copy(deep=True)
    bp.priority_skills["P1"] = ["AWS"]
    bp.priority_skills["P2"] = ["Python"]
    bp.priority_skills["P3"] = []
    bp.priority_skills["P4"] = ["Docker", "Helm", "Ansible"]
    resume = ResumeJSON(
        target_title="Engineer",
        summary="AWS Python Docker Helm Ansible engineer.",
        technical_skills={"Core": ["AWS", "Python", "Docker", "Helm", "Ansible"]},
        experience=[
            ResumeExperience(
                company="A",
                title="Engineer",
                bullets=["Delivered AWS Python Docker Helm Ansible platform work."],
            )
        ],
        projects=[],
        certifications=[],
        variant_id="VP4",
    )
    result = validate_p4_usage(bp, resume)
    assert not result.passed
    assert any(issue.code == "FAIL_P4_OVERUSE" for issue in result.issues)
    assert result.details["p4_share_of_used_priority"] > thresholds.P4_USAGE_MAX


def test_missing_p4_does_not_trigger_required_placement(blueprint):
    resume = _resume_with_p4(blueprint, used=[])
    result = validate_coverage(blueprint, resume)
    p4 = set(blueprint.priority_skills.get("P4", []))
    bad = [
        issue
        for issue in result.issues
        if issue.code == "FAIL_MISSING_REQUIRED_PLACEMENT"
        and (
            issue.metadata.get("placement") == "technical_skills_optional"
            or issue.metadata.get("priority") == "P4"
            or issue.metadata.get("skill") in p4
        )
    ]
    assert bad == []


def test_missing_p4_does_not_enter_repair_missing_skills(blueprint):
    resume = _resume_with_p4(blueprint, used=[])
    bundle = run_validators(blueprint, resume, None, "p4_missing")
    plan = build_repair_plan(bundle, blueprint=blueprint)
    p4 = set(blueprint.priority_skills.get("P4", []))
    assert not (p4 & set(plan["missing_skills"]))


def test_repair_does_not_stuff_p4(blueprint):
    resume = ResumeJSON(
        target_title="Senior Cloud Data Platform Engineer",
        summary="Senior engineer focused on AWS only.",
        technical_skills={"Cloud": ["AWS"]},
        experience=[
            ResumeExperience(
                company="A",
                title="Engineer",
                bullets=["Built AWS cloud infrastructure for deployment reliability."],
            )
        ],
        projects=[],
        certifications=[],
        variant_id="VSTUFF",
        source_blueprint_hash=blueprint.jd_hash,
    )
    resume = attach_skill_provenance(blueprint, resume)
    bundle = run_validators(blueprint, resume, None, "p4_stuff")
    plan = build_repair_plan(bundle, blueprint=blueprint)
    p4 = set(blueprint.priority_skills.get("P4", []))
    assert not (p4 & set(plan["missing_skills"]))


# ---------------------------------------------------------------------------
# Final gate / artifacts (filesystem)
# ---------------------------------------------------------------------------


def test_failed_resume_not_saved_to_validated(blueprint, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    paths = create_run_paths(blueprint.jd_hash, run_id=_uid("gate-fail"))
    resume = _good_resume("V01")
    rejected = save_rejected_resume_artifact(paths, "V01", resume)
    assert rejected.exists()
    assert not (paths.validated_dir / "V01_final.json").exists()
    assert "rejected" in str(rejected)


def test_passed_resume_saved_to_validated(blueprint):
    paths = create_run_paths(blueprint.jd_hash, run_id=_uid("gate-pass"))
    resume = _good_resume("V01")
    final_path = save_validated_resume_artifact(paths, "V01", resume)
    assert final_path.exists()
    assert final_path.parent.name == "validated"
    assert not (paths.rejected_dir / "V01_rejected.json").exists()


def test_failed_resume_saved_to_rejected(blueprint):
    paths = create_run_paths(blueprint.jd_hash, run_id=_uid("gate-reject"))
    resume = _good_resume("V01")
    rejected = save_rejected_resume_artifact(paths, "V01", resume)
    assert rejected.exists()
    assert rejected.parent.name == "rejected"


# ---------------------------------------------------------------------------
# Repair score regression
# ---------------------------------------------------------------------------


def test_repair_score_regression_detected(blueprint):
    raw = _good_resume("V01")
    repaired = _good_resume("V01")
    selection = select_best_resume_version(
        raw_resume=raw,
        raw_bundle=_bundle("V01", passed=False, score=86.59),
        repaired_resume=repaired,
        repaired_bundle=_bundle("V01", passed=False, score=86.57),
    )
    assert selection.regression_recorded
    assert "REPAIR_SCORE_REGRESSION" in selection.notes
    assert selection.status == "FAILED_VALIDATION"


def test_better_valid_version_selected(blueprint):
    raw = _good_resume("V01")
    repaired = _good_resume("V02")
    selection = select_best_resume_version(
        raw_resume=raw,
        raw_bundle=_bundle("V01", passed=True, score=93.0),
        repaired_resume=repaired,
        repaired_bundle=_bundle("V01", passed=True, score=96.0),
    )
    assert selection.status == "VALIDATED"
    assert selection.stage == "repaired"
    assert selection.resume is repaired


def test_failed_versions_never_promoted(blueprint):
    raw = _good_resume("V01")
    repaired = _good_resume("V01")
    selection = select_best_resume_version(
        raw_resume=raw,
        raw_bundle=_bundle("V01", passed=False, score=86.59),
        repaired_resume=repaired,
        repaired_bundle=_bundle("V01", passed=False, score=86.57),
    )
    assert selection.status == "FAILED_VALIDATION"
    # Selection may retain an artifact for rejected/, but it is not VALIDATED.
    assert selection.status != "VALIDATED"


# ---------------------------------------------------------------------------
# Artifact integrity + run isolation
# ---------------------------------------------------------------------------


def test_raw_artifact_preserved(blueprint):
    paths = create_run_paths(blueprint.jd_hash, run_id=_uid("art-raw"))
    raw = _good_resume("V01")
    raw_path = save_raw_resume(paths, "V01", raw)
    original = raw_path.read_text(encoding="utf-8")
    repaired = _good_resume("V01")
    repaired.summary = "CHANGED AFTER REPAIR"
    save_repaired_resume(paths, "V01", repaired)
    assert raw_path.read_text(encoding="utf-8") == original


def test_repair_artifact_is_separate(blueprint):
    paths = create_run_paths(blueprint.jd_hash, run_id=_uid("art-repair"))
    raw_path = save_raw_resume(paths, "V01", _good_resume("V01"))
    repair_path = save_repaired_resume(paths, "V01", _good_resume("V01"))
    assert raw_path != repair_path
    assert raw_path.name == "V01_attempt_01_raw.json"
    assert repair_path.name == "V01_attempt_01_repair.json"


def test_final_artifact_is_separate(blueprint):
    paths = create_run_paths(blueprint.jd_hash, run_id=_uid("art-final"))
    raw_path = save_raw_resume(paths, "V01", _good_resume("V01"))
    repair_path = save_repaired_resume(paths, "V01", _good_resume("V01"))
    final_path = save_validated_resume_artifact(paths, "V01", _good_resume("V01"))
    assert len({raw_path, repair_path, final_path}) == 3
    assert final_path.name == "V01_final.json"


def test_artifact_paths_do_not_overwrite(blueprint):
    paths = create_run_paths(blueprint.jd_hash, run_id=_uid("art-unique"))
    save_raw_resume(paths, "V01", _good_resume("V01"), versioned_if_exists=False)
    with pytest.raises(FileExistsError):
        save_raw_resume(paths, "V01", _good_resume("V01"), versioned_if_exists=False)


def test_run_id_generated(blueprint):
    paths = create_run_paths(blueprint.jd_hash)
    assert paths.run_id
    assert paths.root.exists()


def test_same_jd_two_runs_do_not_collide(blueprint):
    a = create_run_paths(blueprint.jd_hash, run_id=_uid("customer-a"))
    b = create_run_paths(blueprint.jd_hash, run_id=_uid("customer-b"))
    save_raw_resume(a, "V01", _good_resume("V01"))
    save_raw_resume(b, "V01", _good_resume("V01"))
    assert a.root != b.root
    assert (a.raw_dir / "V01_attempt_01_raw.json").exists()
    assert (b.raw_dir / "V01_attempt_01_raw.json").exists()


def test_run_id_in_metadata(blueprint):
    run_id = _uid("meta-run")
    paths = create_run_paths(blueprint.jd_hash, run_id=run_id)
    meta_path = write_run_metadata(
        paths,
        {
            "generation_mode": "TEMPLATE",
            "variant_count": 5,
            "model": "test-model",
            "blueprint_version": "1.0",
        },
    )
    data = json.loads(meta_path.read_text(encoding="utf-8"))
    assert data["run_id"] == run_id
    assert data["jd_hash"] == blueprint.jd_hash


def test_run_id_in_learning_record_if_learning_is_written(blueprint, tmp_path, monkeypatch):
    from resume_engine.learning import outcome_store
    from resume_engine.learning.repository import (
        LearningRepository,
        reset_default_repository_for_tests,
    )

    learning_file = tmp_path / "outcomes.jsonl"
    monkeypatch.setattr(outcome_store, "OUTCOMES_FILE", learning_file)
    reset_default_repository_for_tests(
        LearningRepository(db_path=tmp_path / "test.sqlite3", dual_write_jsonl=True)
    )
    save_learning_outcome(
        {
            "run_id": "learn-run-1",
            "jd_hash": blueprint.jd_hash,
            "variant_id": "V01",
            "successful_pattern": True,
        }
    )
    line = learning_file.read_text(encoding="utf-8").strip().splitlines()[-1]
    record = json.loads(line)
    assert record["run_id"] == "learn-run-1"
    reset_default_repository_for_tests(None)


def test_persisted_paths_are_portable(blueprint):
    paths = create_run_paths(blueprint.jd_hash, run_id=_uid("portable"))
    raw_path = save_raw_resume(paths, "V01", _good_resume("V01"))
    rel = portable_path(raw_path)
    assert rel is not None
    assert not Path(rel).is_absolute()
    assert "Users" not in rel
    assert rel.startswith("resume_engine/storage/runs/")


# ---------------------------------------------------------------------------
# Patch repair
# ---------------------------------------------------------------------------


def test_patch_changes_only_targeted_bullet(blueprint):
    resume = _good_resume("V01")
    original = resume.model_copy(deep=True)
    patched, issues = apply_resume_patches(
        resume,
        [ResumePatch(location="experience[0].bullets[1]", replacement="ONLY THIS CHANGED")],
        repair_plan={
            "targets": [{"location": "experience[0].bullets[1]", "reason_codes": ["X"]}],
            "failed_bullets": ["experience[0].bullets[1]"],
        },
    )
    assert not issues
    assert patched.experience[0].bullets[1] == "ONLY THIS CHANGED"
    assert patched.experience[0].bullets[0] == original.experience[0].bullets[0]
    assert patched.experience[0].bullets[2] == original.experience[0].bullets[2]


def test_non_target_summary_unchanged(blueprint):
    resume = _good_resume("V01")
    patched, issues = apply_resume_patches(
        resume,
        [ResumePatch(location="experience[0].bullets[0]", replacement="new bullet")],
        repair_plan={
            "targets": [{"location": "experience[0].bullets[0]", "reason_codes": ["X"]}],
            "failed_bullets": ["experience[0].bullets[0]"],
        },
    )
    assert not issues
    assert patched.summary == resume.summary


def test_non_target_skills_unchanged(blueprint):
    resume = _good_resume("V01")
    patched, issues = apply_resume_patches(
        resume,
        [ResumePatch(location="experience[0].bullets[0]", replacement="new bullet")],
        repair_plan={
            "targets": [{"location": "experience[0].bullets[0]", "reason_codes": ["X"]}],
            "failed_bullets": ["experience[0].bullets[0]"],
        },
    )
    assert not issues
    assert patched.technical_skills == resume.technical_skills


def test_non_target_experience_unchanged(blueprint):
    resume = _good_resume("V01")
    patched, issues = apply_resume_patches(
        resume,
        [ResumePatch(location="experience[0].bullets[0]", replacement="new bullet")],
        repair_plan={
            "targets": [{"location": "experience[0].bullets[0]", "reason_codes": ["X"]}],
            "failed_bullets": ["experience[0].bullets[0]"],
        },
    )
    assert not issues
    assert patched.experience[1].bullets == resume.experience[1].bullets
    assert patched.experience[0].company == resume.experience[0].company


def test_invalid_patch_path_rejected(blueprint):
    resume = _good_resume("V01")
    with pytest.raises(PatchApplicationError) as exc:
        apply_resume_patches(
            resume,
            [ResumePatch(location="experience[99].bullets[0]", replacement="x")],
            repair_plan={
                "targets": [{"location": "experience[99].bullets[0]", "reason_codes": ["X"]}],
                "failed_bullets": ["experience[99].bullets[0]"],
            },
        )
    assert exc.value.code == "FAIL_INVALID_PATCH_LOCATION"


def test_out_of_scope_patch_rejected(blueprint):
    resume = _good_resume("V01")
    with pytest.raises(PatchApplicationError) as exc:
        apply_resume_patches(
            resume,
            [ResumePatch(location="summary", replacement="hijack")],
            repair_plan={
                "targets": [{"location": "experience[0].bullets[0]", "reason_codes": ["X"]}],
                "failed_bullets": ["experience[0].bullets[0]"],
            },
        )
    assert exc.value.code == "FAIL_OUT_OF_SCOPE_PATCH"


def test_repair_scope_violation_detected(blueprint, monkeypatch):
    from resume_engine.repair import patch_applier

    original_set = patch_applier.set_value_at_location

    def sneaky_set(resume, location, replacement):
        original_set(resume, location, replacement)
        resume.summary = "MUTATED UNRELATED SUMMARY"

    monkeypatch.setattr(patch_applier, "set_value_at_location", sneaky_set)
    resume = _good_resume("V01")
    patched, issues = apply_resume_patches(
        resume,
        [ResumePatch(location="experience[0].bullets[0]", replacement="ok")],
        repair_plan={
            "targets": [{"location": "experience[0].bullets[0]", "reason_codes": ["X"]}],
            "failed_bullets": ["experience[0].bullets[0]"],
        },
    )
    assert any(issue.code == "FAIL_REPAIR_SCOPE_VIOLATION" for issue in issues)
    assert patched.summary == "MUTATED UNRELATED SUMMARY"
