"""
Phase 2.8 Gate 1.1 — shadow evaluation hardening tests.
"""
from __future__ import annotations

import hashlib
import json

import pytest
import river

from resume_engine.learning.online.evaluator import build_shadow_evaluation
from resume_engine.learning.online.feature_builder import build_context_features
from resume_engine.learning.online.policy_store import load_policy, save_policy
from resume_engine.learning.online.replay import replay_from_repository
from resume_engine.learning.online.river_compat import (
    SUPPORTED_RIVER_VERSION,
    RiverLinUCBCompat,
    river_version_supported,
)
from resume_engine.learning.online.river_policy import (
    RiverStrategyPolicy,
    reset_default_policy_for_tests,
)
from resume_engine.learning.online.shadow_runner import (
    effective_mode,
    observe_final_outcome,
    record_shadow_decisions_for_variants,
)
from resume_engine.learning.repository import LearningRepository, reset_default_repository_for_tests
from resume_engine.models.jd_blueprint import (
    BlueprintEntity,
    BlueprintJob,
    GenerationContract,
    JDBlueprint,
)
from resume_engine.strategy.strategy_builder import build_strategy
from resume_engine.strategy.variant_planner import (
    create_variants,
    list_all_candidate_positionings,
    list_eligible_positionings,
)
from tests.fixture_blueprint_builder import get_blueprint


def _mini_blueprint(**overrides) -> JDBlueprint:
    base = {
        "blueprint_version": "1.0",
        "jd_hash": "g11hash",
        "created_at": "2026-01-01T00:00:00Z",
        "job": BlueprintJob(
            target_title="Senior DevOps Engineer",
            primary_family="devops_cloud",
            secondary_family="none",
            seniority="senior",
            hybrid_probability=0.0,
        ),
        "priority_skills": {
            "P1": ["AWS", "Terraform"],
            "P2": ["Kubernetes"],
            "P3": ["Python"],
            "P4": ["Helm"],
        },
        "entities": [
            BlueprintEntity(name="AWS", category="cloud", priority="P1", source="jd"),
            BlueprintEntity(name="Terraform", category="devops", priority="P1", source="jd"),
            BlueprintEntity(name="Kubernetes", category="devops", priority="P2", source="jd"),
        ],
        "responsibilities": ["Deploy Kubernetes on AWS", "Automate CI/CD"],
        "domain_terms": ["cloud"],
        "certifications": [],
        "generation_contract": GenerationContract(
            allowed_technologies=["AWS", "Terraform", "Kubernetes", "Python", "Helm"]
        ),
    }
    base.update(overrides)
    return JDBlueprint.model_validate(base)


def _good_record(**overrides) -> dict:
    record = {
        "run_id": "r-g11",
        "jd_hash": "g11hash",
        "variant_id": "V01",
        "variant_positioning": "cloud_infrastructure",
        "primary_family": "devops_cloud",
        "secondary_family": "none",
        "seniority": "senior",
        "passed": True,
        "is_final_selection": True,
        "superseded": False,
        "eligible_for_learning": True,
        "technology_firewall_passed": True,
        "role_drift_passed": True,
        "p1_coverage": 100.0,
        "p2_coverage": 95.0,
        "responsibility_coverage": 90.0,
        "role_alignment": 90.0,
        "technology_alignment": 100.0,
        "laya_alignment": 85.0,
        "variant_focus_score": 80.0,
        "duplicate_score": 95.0,
        "cross_run_uniqueness": 100.0,
        "repair_count": 0,
        "p4_usage": 100.0,
        "status": "VALIDATED",
    }
    record.update(overrides)
    return record


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    reset_default_policy_for_tests()
    monkeypatch.setenv("RESUME_ONLINE_LEARNING_MODE", "shadow")
    monkeypatch.setattr(
        "resume_engine.learning.online.policy_store.ONLINE_LEARNING_STORAGE_DIR",
        tmp_path / "online",
    )
    monkeypatch.setattr(
        "resume_engine.config.settings.ONLINE_LEARNING_STORAGE_DIR",
        tmp_path / "online",
    )
    repo = LearningRepository(db_path=tmp_path / "learning.sqlite3", dual_write_jsonl=False)
    reset_default_repository_for_tests(repo)
    yield
    reset_default_repository_for_tests(None)
    reset_default_policy_for_tests()


# --- Decision linkage ---


def test_shadow_decision_returns_database_id():
    bp = _mini_blueprint()
    decisions = record_shadow_decisions_for_variants(
        blueprint=bp,
        production_variants=[("V01", "cloud_infrastructure")],
        run_id="link-1",
    )
    assert decisions
    assert decisions[0].decision_id is not None
    assert decisions[0].decision_id > 0


def test_one_decision_saved_per_production_variant():
    bp = _mini_blueprint()
    decisions = record_shadow_decisions_for_variants(
        blueprint=bp,
        production_variants=[
            ("V01", "cloud_infrastructure"),
            ("V02", "platform_reliability"),
            ("V03", "automation_iac"),
        ],
        run_id="link-multi",
    )
    assert len(decisions) == 3
    assert {d.variant_id for d in decisions} == {"V01", "V02", "V03"}


def test_final_observation_links_to_matching_decision():
    bp = _mini_blueprint()
    decisions = record_shadow_decisions_for_variants(
        blueprint=bp,
        production_variants=[("V01", "cloud_infrastructure")],
        run_id="link-obs",
    )
    obs = observe_final_outcome(
        blueprint=bp,
        learning_record=_good_record(run_id="link-obs", variant_id="V01"),
        policy=RiverStrategyPolicy(seed=1),
        persist_policy=False,
    )
    assert obs is not None
    assert obs["decision_id"] == decisions[0].decision_id
    assert obs["linkage_status"] == "linked"


def test_v01_observation_does_not_link_to_v02_decision():
    bp = _mini_blueprint()
    decisions = record_shadow_decisions_for_variants(
        blueprint=bp,
        production_variants=[
            ("V01", "cloud_infrastructure"),
            ("V02", "platform_reliability"),
        ],
        run_id="link-cross",
    )
    obs = observe_final_outcome(
        blueprint=bp,
        learning_record=_good_record(
            run_id="link-cross",
            variant_id="V01",
            variant_positioning="cloud_infrastructure",
        ),
        policy=RiverStrategyPolicy(seed=1),
        persist_policy=False,
    )
    assert obs["decision_id"] == decisions[0].decision_id
    assert obs["decision_id"] != decisions[1].decision_id


def test_missing_decision_does_not_break_phase2():
    bp = _mini_blueprint()
    obs = observe_final_outcome(
        blueprint=bp,
        learning_record=_good_record(run_id="no-dec", variant_id="V09"),
        policy=RiverStrategyPolicy(seed=1),
        persist_policy=False,
    )
    assert obs is not None
    assert obs["decision_id"] is None
    assert obs["linkage_status"] == "decision_not_found"


def test_decision_lookup_uses_run_and_variant():
    from resume_engine.learning.repository import get_default_repository

    bp = _mini_blueprint()
    record_shadow_decisions_for_variants(
        blueprint=bp,
        production_variants=[("V01", "cloud_infrastructure")],
        run_id="lookup-a",
    )
    record_shadow_decisions_for_variants(
        blueprint=bp,
        production_variants=[("V01", "cloud_infrastructure")],
        run_id="lookup-b",
    )
    repo = get_default_repository()
    a = repo.get_online_decision(run_id="lookup-a", variant_id="V01")
    b = repo.get_online_decision(run_id="lookup-b", variant_id="V01")
    assert a is not None and b is not None
    assert a["id"] != b["id"]


def test_decision_id_persisted_in_observation():
    from resume_engine.learning.repository import get_default_repository

    bp = _mini_blueprint()
    decisions = record_shadow_decisions_for_variants(
        blueprint=bp,
        production_variants=[("V01", "cloud_infrastructure")],
        run_id="persist-id",
    )
    observe_final_outcome(
        blueprint=bp,
        learning_record=_good_record(run_id="persist-id", variant_id="V01"),
        policy=RiverStrategyPolicy(seed=2),
        persist_policy=False,
    )
    rows = get_default_repository().list_online_observations()
    match = [r for r in rows if r["run_id"] == "persist-id"]
    assert match
    assert match[0]["decision_id"] == decisions[0].decision_id


def test_decision_observation_join_roundtrip():
    from resume_engine.learning.repository import get_default_repository

    bp = _mini_blueprint()
    decisions = record_shadow_decisions_for_variants(
        blueprint=bp,
        production_variants=[("V01", "cloud_infrastructure")],
        run_id="join-1",
    )
    observe_final_outcome(
        blueprint=bp,
        learning_record=_good_record(run_id="join-1", variant_id="V01"),
        policy=RiverStrategyPolicy(seed=2),
        persist_policy=False,
    )
    repo = get_default_repository()
    obs = next(r for r in repo.list_online_observations() if r["run_id"] == "join-1")
    decision = repo.get_online_decision(run_id="join-1", variant_id="V01")
    assert obs["decision_id"] == decision["id"] == decisions[0].decision_id


# --- Analytics ---


def test_shadow_evaluator_empty_database():
    evaluation = build_shadow_evaluation()
    assert evaluation.total_decisions == 0
    assert evaluation.insufficient_evidence is True
    assert evaluation.activation_ready is False


def test_shadow_agreement_rate():
    bp = _mini_blueprint()
    record_shadow_decisions_for_variants(
        blueprint=bp,
        production_variants=[("V01", "cloud_infrastructure")],
        run_id="agr-1",
        policy=RiverStrategyPolicy(seed=42),
    )
    evaluation = build_shadow_evaluation()
    assert evaluation.total_decisions >= 1
    assert evaluation.shadow_agreement_rate is not None


def test_mean_reward_when_shadow_agrees():
    bp = _mini_blueprint()
    decisions = record_shadow_decisions_for_variants(
        blueprint=bp,
        production_variants=[("V01", "cloud_infrastructure")],
        run_id="rew-a",
        policy=RiverStrategyPolicy(seed=42),
    )
    observe_final_outcome(
        blueprint=bp,
        learning_record=_good_record(run_id="rew-a", variant_id="V01"),
        policy=RiverStrategyPolicy(seed=42),
        persist_policy=False,
    )
    evaluation = build_shadow_evaluation()
    if decisions and decisions[0].shadow_agrees_with_production:
        assert evaluation.mean_reward_when_shadow_agrees is not None


def test_mean_reward_when_shadow_disagrees():
    evaluation = build_shadow_evaluation()
    # May be None with empty/agree-only data — just ensure field exists.
    assert hasattr(evaluation, "mean_reward_when_shadow_disagrees")


def test_per_action_metrics():
    bp = _mini_blueprint()
    record_shadow_decisions_for_variants(
        blueprint=bp,
        production_variants=[("V01", "cloud_infrastructure")],
        run_id="act-1",
    )
    evaluation = build_shadow_evaluation()
    assert "cloud_infrastructure" in evaluation.per_action


def test_per_family_metrics():
    bp = _mini_blueprint()
    record_shadow_decisions_for_variants(
        blueprint=bp,
        production_variants=[("V01", "cloud_infrastructure")],
        run_id="fam-1",
    )
    observe_final_outcome(
        blueprint=bp,
        learning_record=_good_record(run_id="fam-1", variant_id="V01"),
        policy=RiverStrategyPolicy(seed=1),
        persist_policy=False,
    )
    evaluation = build_shadow_evaluation()
    assert evaluation.per_primary_family


def test_unlinked_observations_reported():
    bp = _mini_blueprint()
    observe_final_outcome(
        blueprint=bp,
        learning_record=_good_record(run_id="unlinked", variant_id="V01"),
        policy=RiverStrategyPolicy(seed=1),
        persist_policy=False,
    )
    evaluation = build_shadow_evaluation()
    assert evaluation.unlinked_observations >= 1


def test_insufficient_evidence_below_threshold():
    evaluation = build_shadow_evaluation()
    assert evaluation.insufficient_evidence is True


def test_activation_ready_not_used_to_enable_active_mode(monkeypatch):
    monkeypatch.setenv("RESUME_ONLINE_LEARNING_MODE", "active")
    assert effective_mode() == "shadow"
    evaluation = build_shadow_evaluation()
    assert evaluation.activation_ready is False


def test_evaluation_report_does_not_modify_policy(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "resume_engine.learning.online.policy_store.ONLINE_LEARNING_STORAGE_DIR",
        tmp_path / "online",
    )
    policy = RiverStrategyPolicy(seed=9)
    save_policy(policy)
    before = (tmp_path / "online" / "policy.pkl").read_bytes()
    build_shadow_evaluation()
    after = (tmp_path / "online" / "policy.pkl").read_bytes()
    assert before == after


# --- Sparse / fallback ---


def test_sparse_jd_production_actions_are_shadow_eligible():
    bp = get_blueprint("12_sparse_poor_jd")
    strategy = build_strategy(bp)
    variants = create_variants(bp, strategy)
    candidates = set(list_all_candidate_positionings(bp))
    assert candidates
    assert {v.positioning for v in variants}.issubset(candidates)


def test_fallback_positioning_is_not_rejected_by_shadow_runner():
    bp = get_blueprint("12_sparse_poor_jd")
    strategy = build_strategy(bp)
    variants = create_variants(bp, strategy)
    decisions = record_shadow_decisions_for_variants(
        blueprint=bp,
        production_variants=[(v.variant_id, v.positioning) for v in variants],
        run_id="sparse-1",
    )
    assert len(decisions) == len(variants)


def test_online_action_set_matches_production_possible_actions():
    bp = get_blueprint("02_pure_devops")
    candidates = list_all_candidate_positionings(bp)
    eligible_only = list_eligible_positionings(bp)
    assert set(eligible_only).issubset(set(candidates))
    strategy = build_strategy(bp)
    for v in create_variants(bp, strategy):
        assert v.positioning in candidates


def test_single_action_context_supported():
    bp = _mini_blueprint()
    decisions = record_shadow_decisions_for_variants(
        blueprint=bp,
        production_variants=[("V01", "cloud_infrastructure")],
        run_id="single-1",
        policy=RiverStrategyPolicy(seed=1),
    )
    # Force single available by ranking one action path via decision fields
    assert decisions[0].shadow_top_action is not None


def test_river_still_cannot_invent_fallback_action():
    policy = RiverStrategyPolicy(seed=1)
    ranked = policy.rank_actions(build_context_features(_mini_blueprint()), ["cloud_infrastructure"])
    assert ranked[0].action == "cloud_infrastructure"
    assert all(p.action == "cloud_infrastructure" for p in ranked)


# --- Idempotency ---


def test_same_final_observation_not_trained_twice():
    bp = _mini_blueprint()
    policy = RiverStrategyPolicy(seed=3)
    record = _good_record(run_id="idem-1", variant_id="V01")
    observe_final_outcome(blueprint=bp, learning_record=record, policy=policy, persist_policy=False)
    before = policy.observation_count
    second = observe_final_outcome(
        blueprint=bp, learning_record=record, policy=policy, persist_policy=False
    )
    assert second.get("duplicate_observation_skipped") is True
    assert policy.observation_count == before


def test_duplicate_observation_count_stays_one():
    from resume_engine.learning.repository import get_default_repository

    bp = _mini_blueprint()
    policy = RiverStrategyPolicy(seed=3)
    record = _good_record(run_id="idem-2", variant_id="V01")
    observe_final_outcome(blueprint=bp, learning_record=record, policy=policy, persist_policy=False)
    observe_final_outcome(blueprint=bp, learning_record=record, policy=policy, persist_policy=False)
    applied = [
        r
        for r in get_default_repository().list_online_observations()
        if r["run_id"] == "idem-2" and r.get("train_status") == "APPLIED"
    ]
    assert len(applied) == 1


def test_policy_observation_count_not_incremented_twice():
    bp = _mini_blueprint()
    policy = RiverStrategyPolicy(seed=4)
    record = _good_record(run_id="idem-3", variant_id="V01")
    observe_final_outcome(blueprint=bp, learning_record=record, policy=policy, persist_policy=False)
    observe_final_outcome(blueprint=bp, learning_record=record, policy=policy, persist_policy=False)
    assert policy.observation_count == 1


def test_different_variants_same_run_can_each_train_once():
    bp = _mini_blueprint()
    policy = RiverStrategyPolicy(seed=5)
    candidates = list_all_candidate_positionings(bp)
    a1, a2 = candidates[0], candidates[1] if len(candidates) > 1 else candidates[0]
    observe_final_outcome(
        blueprint=bp,
        learning_record=_good_record(run_id="idem-4", variant_id="V01", variant_positioning=a1),
        policy=policy,
        persist_policy=False,
    )
    observe_final_outcome(
        blueprint=bp,
        learning_record=_good_record(run_id="idem-4", variant_id="V02", variant_positioning=a2),
        policy=policy,
        persist_policy=False,
    )
    assert policy.observation_count == 2


def test_same_variant_different_run_can_train():
    bp = _mini_blueprint()
    policy = RiverStrategyPolicy(seed=6)
    observe_final_outcome(
        blueprint=bp,
        learning_record=_good_record(run_id="run-a", variant_id="V01"),
        policy=policy,
        persist_policy=False,
    )
    observe_final_outcome(
        blueprint=bp,
        learning_record=_good_record(run_id="run-b", variant_id="V01"),
        policy=policy,
        persist_policy=False,
    )
    assert policy.observation_count == 2


# --- Compatibility ---


def test_supported_river_version():
    assert river.__version__ == SUPPORTED_RIVER_VERSION
    assert river_version_supported() is True


def test_river_private_api_isolation():
    import inspect

    import resume_engine.learning.online.river_policy as policy_mod

    source = inspect.getsource(policy_mod)
    assert "_bayes_lin_regs" not in source
    compat = RiverLinUCBCompat(RiverStrategyPolicy(seed=1)._model)
    score = compat.score_action("cloud_infrastructure", build_context_features(_mini_blueprint()))
    assert isinstance(score, float)


def test_policy_adapter_falls_back_if_scoring_api_missing():
    policy = RiverStrategyPolicy(seed=1)
    policy._scoring_available = False
    ranked = policy.rank_actions(build_context_features(_mini_blueprint()), ["b", "a"])
    assert [p.action for p in ranked] == ["a", "b"]


def test_policy_failure_does_not_change_production_variants(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("forced")

    monkeypatch.setattr(
        "resume_engine.learning.online.shadow_runner.build_context_features",
        boom,
    )
    bp = get_blueprint("02_pure_devops")
    strategy = build_strategy(bp)
    baseline = [v.positioning for v in create_variants(bp, strategy)]
    decisions = record_shadow_decisions_for_variants(
        blueprint=bp,
        production_variants=[("V01", baseline[0])],
        run_id="fail-1",
    )
    assert decisions == []
    assert [v.positioning for v in create_variants(bp, strategy)] == baseline


def test_incompatible_policy_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "resume_engine.learning.online.policy_store.ONLINE_LEARNING_STORAGE_DIR",
        tmp_path / "online",
    )
    policy = RiverStrategyPolicy(seed=1)
    save_policy(policy)
    meta_path = tmp_path / "online" / "policy_metadata.json"
    meta = json.loads(meta_path.read_text())
    meta["feature_schema_version"] = "online-features-OLD"
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    assert load_policy(directory=tmp_path / "online") is None


# --- Replay / production invariants ---


def test_replay_dry_run_preserves_policy_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "resume_engine.learning.online.policy_store.ONLINE_LEARNING_STORAGE_DIR",
        tmp_path / "online",
    )
    policy = RiverStrategyPolicy(seed=8)
    save_policy(policy)
    before = hashlib.sha256((tmp_path / "online" / "policy.pkl").read_bytes()).hexdigest()
    replay_from_repository(dry_run=True, policy=RiverStrategyPolicy(seed=8))
    after = hashlib.sha256((tmp_path / "online" / "policy.pkl").read_bytes()).hexdigest()
    assert before == after


def test_replay_reports_skip_reasons():
    from resume_engine.learning.repository import get_default_repository

    get_default_repository().save_outcome(
        {
            "run_id": "thin",
            "jd_hash": "h",
            "variant_id": "V01",
            "variant_positioning": "cloud_infrastructure",
            "passed": True,
            "eligible_for_learning": True,
            "is_final_selection": True,
            "p1_coverage": 100.0,
            "p2_coverage": 95.0,
            "technology_firewall_passed": True,
            "role_drift_passed": True,
        }
    )
    report = replay_from_repository(dry_run=True)
    assert report.skip_reasons
    assert "missing_context" in report.skip_reasons or "ineligible" in report.skip_reasons


def test_shadow_does_not_alter_variant_order(monkeypatch):
    bp = get_blueprint("02_pure_devops")
    strategy = build_strategy(bp)
    monkeypatch.setenv("RESUME_ONLINE_LEARNING_MODE", "disabled")
    baseline = [v.positioning for v in create_variants(bp, strategy)]
    monkeypatch.setenv("RESUME_ONLINE_LEARNING_MODE", "shadow")
    shadowed = [v.positioning for v in create_variants(bp, strategy)]
    assert shadowed == baseline


def test_active_env_still_falls_back_to_shadow(monkeypatch):
    monkeypatch.setenv("RESUME_ONLINE_LEARNING_MODE", "active")
    assert effective_mode() == "shadow"


def test_online_cannot_change_allowed_technologies():
    bp = get_blueprint("02_pure_devops")
    strategy = build_strategy(bp)
    before = list(strategy.allowed_tools)
    record_shadow_decisions_for_variants(
        blueprint=bp,
        production_variants=[("V01", create_variants(bp, strategy)[0].positioning)],
        run_id="tech-1",
    )
    assert list(build_strategy(bp).allowed_tools) == before
