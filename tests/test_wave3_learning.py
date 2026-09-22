"""
Wave 3 self-learning tests.

Covers richer outcomes, eligibility, retrieval, min-sample guard,
family-scoped ranking feedback, and no new technology introduction.
"""
from __future__ import annotations

import json
from pathlib import Path

from resume_engine.config import thresholds
from resume_engine.learning.eligibility import is_record_eligible_for_learning
from resume_engine.learning.outcome_builder import build_learning_outcome
from resume_engine.learning.strategy_memory import (
    retrieve_strategy_insights,
    summarize_strategy_memory,
)
from resume_engine.models.resume_strategy import VariantStrategy
from resume_engine.models.validation_schema import (
    ValidationBundle,
    ValidationIssue,
    ValidatorResult,
)
from resume_engine.strategy.strategy_builder import build_strategy
from resume_engine.strategy.variant_planner import create_variants, select_angle_templates
from tests.fixture_blueprint_builder import get_blueprint


def _eligible_record(
    *,
    primary_family: str = "devops_cloud",
    secondary_family: str = "none",
    hybrid: bool = False,
    seniority: str = "senior",
    positioning: str = "platform_reliability",
    score: float = 96.0,
    passed: bool = True,
    failure_codes: list[str] | None = None,
    p1: float = 100.0,
    p2: float = 95.0,
) -> dict:
    return {
        "passed": passed,
        "successful_pattern": passed,
        "primary_family": primary_family,
        "secondary_family": secondary_family,
        "hybrid": hybrid,
        "seniority": seniority,
        "variant_positioning": positioning,
        "score_after": score,
        "score_after_repair": score,
        "p1_coverage": p1,
        "p2_coverage": p2,
        "failure_codes": failure_codes or [],
        "technology_firewall_passed": True,
        "role_drift_passed": True,
    }


def _write_outcomes(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")


def _positionings(blueprint, outcomes_path: Path | None) -> list[str]:
    strategy = build_strategy(blueprint)
    variants = create_variants(blueprint, strategy, outcomes_path=outcomes_path)
    return [variant.positioning for variant in variants]


# ---------------------------------------------------------------------------
# Eligibility
# ---------------------------------------------------------------------------


def test_failed_runs_not_eligible():
    record = _eligible_record(passed=False, score=99.0)
    assert is_record_eligible_for_learning(record) is False


def test_firewall_error_not_eligible_even_if_passed_flag():
    record = _eligible_record(
        passed=True,
        failure_codes=["FAIL_UNAPPROVED_TECHNOLOGY"],
    )
    assert is_record_eligible_for_learning(record) is False


def test_role_drift_not_eligible():
    record = _eligible_record(failure_codes=["FAIL_ROLE_DRIFT"])
    assert is_record_eligible_for_learning(record) is False


def test_low_p1_not_eligible():
    record = _eligible_record(p1=90.0)
    assert is_record_eligible_for_learning(record) is False


def test_low_p2_not_eligible():
    record = _eligible_record(p2=80.0)
    assert is_record_eligible_for_learning(record) is False


def test_strong_success_is_eligible():
    assert is_record_eligible_for_learning(_eligible_record()) is True


# ---------------------------------------------------------------------------
# Mission-required learning tests
# ---------------------------------------------------------------------------


def test_failed_runs_not_used_for_strategy_learning(tmp_path: Path):
    bp = get_blueprint("02_pure_devops")
    baseline = _positionings(bp, outcomes_path=tmp_path / "empty.jsonl")

    outcomes = tmp_path / "outcomes.jsonl"
    _write_outcomes(
        outcomes,
        [
            _eligible_record(passed=False, positioning="platform_reliability", score=99.0)
            for _ in range(thresholds.LEARNING_MIN_SAMPLE_COUNT + 2)
        ],
    )
    after = _positionings(bp, outcomes_path=outcomes)
    assert after == baseline


def test_insufficient_history_does_not_change_strategy(tmp_path: Path):
    bp = get_blueprint("02_pure_devops")
    baseline = _positionings(bp, outcomes_path=tmp_path / "empty.jsonl")

    outcomes = tmp_path / "outcomes.jsonl"
    # One below the minimum — must not reorder.
    _write_outcomes(
        outcomes,
        [
            _eligible_record(positioning="platform_reliability", score=99.0)
            for _ in range(thresholds.LEARNING_MIN_SAMPLE_COUNT - 1)
        ],
    )
    insights = retrieve_strategy_insights(bp, outcomes_path=outcomes)
    assert insights["applied"] is False
    assert insights["eligible_sample_count"] == thresholds.LEARNING_MIN_SAMPLE_COUNT - 1
    after = _positionings(bp, outcomes_path=outcomes)
    assert after == baseline


def test_successful_history_changes_variant_ranking(tmp_path: Path):
    bp = get_blueprint("02_pure_devops")
    baseline = _positionings(bp, outcomes_path=tmp_path / "empty.jsonl")
    assert baseline[0] == "cloud_infrastructure"
    assert "platform_reliability" in baseline
    baseline_platform_index = baseline.index("platform_reliability")

    outcomes = tmp_path / "outcomes.jsonl"
    _write_outcomes(
        outcomes,
        [
            _eligible_record(positioning="platform_reliability", score=99.0)
            for _ in range(thresholds.LEARNING_MIN_SAMPLE_COUNT)
        ],
    )
    insights = retrieve_strategy_insights(bp, outcomes_path=outcomes)
    assert insights["applied"] is True
    assert insights["eligible_sample_count"] >= thresholds.LEARNING_MIN_SAMPLE_COUNT

    after = _positionings(bp, outcomes_path=outcomes)
    assert after != baseline
    assert after.index("platform_reliability") < baseline_platform_index
    # Still a valid family angle set — learning reorders, does not invent catalogs.
    assert set(after).issubset(
        {
            "cloud_infrastructure",
            "automation_iac",
            "cloud_support",
            "container_orchestration",
            "platform_reliability",
            "cloud_data_engineering",
            "application_reliability",
            "orchestration_reliability",
            "ai_enabled_operations",
            "support_automation",
            "reliability_support",
        }
    )


def test_learning_scoped_by_family(tmp_path: Path):
    bp = get_blueprint("02_pure_devops")
    baseline = _positionings(bp, outcomes_path=tmp_path / "empty.jsonl")

    outcomes = tmp_path / "outcomes.jsonl"
    # Successful history for a different primary family must not move devops ranking.
    _write_outcomes(
        outcomes,
        [
            _eligible_record(
                primary_family="data_analytics",
                positioning="platform_reliability",
                score=99.0,
            )
            for _ in range(thresholds.LEARNING_MIN_SAMPLE_COUNT)
        ],
    )
    insights = retrieve_strategy_insights(bp, outcomes_path=outcomes)
    assert insights["applied"] is False
    assert insights["eligible_sample_count"] == 0
    after = _positionings(bp, outcomes_path=outcomes)
    assert after == baseline


def test_learning_does_not_introduce_new_technology(tmp_path: Path):
    bp = get_blueprint("02_pure_devops")
    strategy = build_strategy(bp)
    allowed = set(strategy.allowed_tools)

    outcomes = tmp_path / "outcomes.jsonl"
    _write_outcomes(
        outcomes,
        [
            _eligible_record(positioning="platform_reliability", score=99.0)
            for _ in range(thresholds.LEARNING_MIN_SAMPLE_COUNT)
        ],
    )
    variants = create_variants(bp, strategy, outcomes_path=outcomes)
    assert any(
        "Historical eligible learning applied" in rule
        for variant in variants
        for rule in variant.rules
    )
    for variant in variants:
        assert set(variant.emphasis).issubset(allowed)
        assert "Spark" not in variant.emphasis
        assert "Databricks" not in variant.emphasis
        assert "HallucinatedToolX" not in variant.emphasis


# ---------------------------------------------------------------------------
# Richer outcomes + summary
# ---------------------------------------------------------------------------


def test_richer_outcome_schema_fields():
    bp = get_blueprint("02_pure_devops")
    variant = VariantStrategy(
        variant_id="V01",
        positioning="cloud_infrastructure",
        description="test",
    )
    issue = ValidationIssue(
        code="FAIL_MISSING_REQUIRED_PLACEMENT",
        severity="warning",
        message="optional warning",
    )
    before = ValidationBundle(
        variant_id="V01",
        resume_id="r1",
        passed=False,
        optimization_score=90.0,
        action="REPAIR_REQUIRED",
        subscores={"p1_coverage": 100.0, "p2_coverage": 92.0},
        validator_results=[
            ValidatorResult(name="coverage_validator", passed=False, issues=[issue]),
            ValidatorResult(name="technology_firewall", passed=True),
            ValidatorResult(name="role_drift_validator", passed=True),
        ],
    )
    after = ValidationBundle(
        variant_id="V01",
        resume_id="r1",
        passed=True,
        optimization_score=94.0,
        action="PASS",
        subscores={
            "p1_coverage": 100.0,
            "p2_coverage": 95.0,
            "responsibility_coverage": 90.0,
            "role_alignment": 92.0,
            "technology_alignment": 100.0,
            "bullet_quality": 88.0,
            "duplicate_safety": 100.0,
            "p4_usage": 100.0,
        },
        validator_results=[
            ValidatorResult(name="coverage_validator", passed=True),
            ValidatorResult(name="technology_firewall", passed=True),
            ValidatorResult(name="role_drift_validator", passed=True),
        ],
    )
    record = build_learning_outcome(
        blueprint=bp,
        variant=variant,
        run_id="run-1",
        strategy_id="strategy_x",
        before_bundle=before,
        selection_bundle=after,
        passed=True,
        status="VALIDATED",
        repaired=True,
        regression_recorded=False,
        selection_notes=[],
        diagnostics={"variant_focus_score": 0.8},
        model="gpt-test",
    )
    required = {
        "run_id",
        "jd_hash",
        "primary_family",
        "secondary_family",
        "hybrid",
        "seniority",
        "variant_positioning",
        "p1_coverage",
        "p2_coverage",
        "responsibility_coverage",
        "role_alignment",
        "technology_alignment",
        "laya_alignment",
        "duplicate_score",
        "p4_usage",
        "score_before",
        "score_after",
        "passed",
        "repair_count",
        "failure_codes",
        "successful_repairs",
        "variant_diversity",
        "prompt_version",
        "model",
        "eligible_for_learning",
    }
    assert required.issubset(record.keys())
    assert record["repair_count"] == 1
    assert record["eligible_for_learning"] is True
    assert record["model"] == "gpt-test"
    assert "FAIL_MISSING_REQUIRED_PLACEMENT" in record["successful_repairs"]


def test_strategy_memory_summary_excludes_ineligible(tmp_path: Path, monkeypatch):
    from resume_engine.learning import strategy_memory as sm

    outcomes = tmp_path / "outcomes.jsonl"
    _write_outcomes(
        outcomes,
        [
            _eligible_record(positioning="cloud_infrastructure", score=95.0),
            _eligible_record(passed=False, positioning="automation_iac", score=99.0),
        ],
    )
    monkeypatch.setattr(sm, "OUTCOMES_FILE", outcomes)
    eligible = summarize_strategy_memory(eligible_only=True)
    all_records = summarize_strategy_memory(eligible_only=False)
    assert any("cloud_infrastructure" in key for key in eligible)
    assert not any("automation_iac" in key for key in eligible)
    assert any("automation_iac" in key for key in all_records)


def test_learning_min_sample_constant_documented():
    assert thresholds.LEARNING_MIN_SAMPLE_COUNT == 5
    assert thresholds.LEARNING_HISTORICAL_WEIGHT > 0


def test_select_angles_accepts_injected_insights():
    bp = get_blueprint("02_pure_devops")
    baseline = select_angle_templates(
        bp,
        learning_insights={
            "applied": False,
            "eligible_sample_count": 0,
            "min_sample_count": 5,
            "positioning_scores": {},
            "historical_weight": 0.0,
        },
    )
    boosted = select_angle_templates(
        bp,
        learning_insights={
            "applied": True,
            "eligible_sample_count": 5,
            "min_sample_count": 5,
            "positioning_scores": {
                "platform_reliability": {"average_score": 99.0, "count": 5},
            },
            "historical_weight": thresholds.LEARNING_HISTORICAL_WEIGHT,
        },
    )
    assert [a.positioning for a in boosted] != [a.positioning for a in baseline]
