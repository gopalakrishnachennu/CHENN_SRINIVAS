"""
Phase 2.8 Gate 1 — River online learning (shadow mode) tests.
"""
from __future__ import annotations

import pytest
import river

from resume_engine.learning.online import config as online_config
from resume_engine.learning.online.feature_builder import (
    PII_KEYS,
    assert_no_pii,
    build_context_features,
)
from resume_engine.learning.online.policy_store import load_policy, policy_dir, save_policy
from resume_engine.learning.online.replay import replay_from_repository
from resume_engine.learning.online.reward_engine import compute_reward
from resume_engine.learning.online.river_policy import (
    RiverStrategyPolicy,
    reset_default_policy_for_tests,
)
from resume_engine.learning.online.shadow_runner import (
    observe_final_outcome,
    record_shadow_decision,
)
from resume_engine.learning.repository import LearningRepository, reset_default_repository_for_tests
from resume_engine.models.jd_blueprint import (
    BlueprintEntity,
    BlueprintJob,
    GenerationContract,
    JDBlueprint,
)
from resume_engine.strategy.strategy_builder import build_strategy
from resume_engine.strategy.variant_planner import create_variants, list_eligible_positionings
from tests.fixture_blueprint_builder import get_blueprint


def _mini_blueprint(**overrides) -> JDBlueprint:
    base = {
        "blueprint_version": "1.0",
        "jd_hash": "onlinehash",
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
        "generation_contract": GenerationContract(allowed_technologies=["AWS", "Terraform", "Kubernetes", "Python", "Helm"]),
    }
    base.update(overrides)
    return JDBlueprint.model_validate(base)


def _good_record(**overrides) -> dict:
    record = {
        "run_id": "r1",
        "jd_hash": "onlinehash",
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
def _isolate_online(tmp_path, monkeypatch):
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


# ---------------------------------------------------------------------------
# Dependency / features
# ---------------------------------------------------------------------------


def test_river_version_expected():
    assert river.__version__ == "0.26.1"


def test_feature_builder_is_deterministic():
    bp = _mini_blueprint()
    a = build_context_features(bp)
    b = build_context_features(bp)
    assert a == b


def test_feature_builder_contains_no_candidate_pii():
    features = build_context_features(_mini_blueprint())
    assert_no_pii(features)
    assert not ({k.lower() for k in features} & PII_KEYS)


def test_feature_builder_primary_family_encoding():
    features = build_context_features(_mini_blueprint())
    assert features["primary_family_devops_cloud"] == 1.0
    assert features["primary_family_data_engineering"] == 0.0


def test_feature_builder_hybrid_features():
    bp = _mini_blueprint(
        job=BlueprintJob(
            target_title="Hybrid",
            primary_family="devops_cloud",
            secondary_family="data_engineering",
            seniority="senior",
            hybrid_probability=0.8,
        )
    )
    features = build_context_features(bp)
    assert features["is_hybrid"] == 1.0
    assert features["hybrid_probability"] == 0.8


# ---------------------------------------------------------------------------
# Policy actions
# ---------------------------------------------------------------------------


def test_policy_only_ranks_eligible_actions():
    policy = RiverStrategyPolicy(seed=42)
    ctx = build_context_features(_mini_blueprint())
    actions = ["cloud_infrastructure", "platform_reliability"]
    ranked = policy.rank_actions(ctx, actions)
    assert [p.action for p in ranked] == sorted(
        [p.action for p in ranked], key=lambda a: ([x.action for x in ranked].index(a))
    )
    assert {p.action for p in ranked}.issubset(set(actions))


def test_policy_cannot_invent_action():
    policy = RiverStrategyPolicy(seed=42)
    ctx = build_context_features(_mini_blueprint())
    ranked = policy.rank_actions(ctx, ["cloud_infrastructure"])
    assert ranked[0].action == "cloud_infrastructure"
    assert all(p.probability is None for p in ranked)


def test_policy_same_seed_reproducible_where_applicable():
    ctx = build_context_features(_mini_blueprint())
    actions = ["cloud_infrastructure", "platform_reliability", "automation_iac"]
    a = RiverStrategyPolicy(seed=42).rank_actions(ctx, actions)
    b = RiverStrategyPolicy(seed=42).rank_actions(ctx, actions)
    assert [p.action for p in a] == [p.action for p in b]


# ---------------------------------------------------------------------------
# Rewards
# ---------------------------------------------------------------------------


def test_reward_is_bounded_zero_one():
    result = compute_reward(_good_record())
    assert 0.0 <= result.reward <= 1.0
    assert result.trainable is True


def test_failed_resume_reward_zero():
    result = compute_reward(_good_record(passed=False))
    assert result.reward == 0.0
    assert result.trainable is False


def test_firewall_failure_reward_zero():
    result = compute_reward(_good_record(technology_firewall_passed=False))
    assert result.reward == 0.0


def test_p1_failure_reward_zero():
    result = compute_reward(_good_record(p1_coverage=90.0))
    assert result.reward == 0.0


def test_superseded_variant_not_trainable():
    result = compute_reward(_good_record(superseded=True))
    assert result.trainable is False
    assert result.reward == 0.0


def test_non_final_variant_not_trainable():
    result = compute_reward(_good_record(is_final_selection=False))
    assert result.trainable is False


def test_good_final_resume_positive_reward():
    result = compute_reward(_good_record())
    assert result.trainable is True
    assert result.reward > 0.5


# ---------------------------------------------------------------------------
# Shadow mode
# ---------------------------------------------------------------------------


def test_shadow_mode_does_not_change_production_variant_order(monkeypatch):
    bp = get_blueprint("02_pure_devops")
    strategy = build_strategy(bp)
    monkeypatch.setenv("RESUME_ONLINE_LEARNING_MODE", "disabled")
    baseline = [v.positioning for v in create_variants(bp, strategy)]
    monkeypatch.setenv("RESUME_ONLINE_LEARNING_MODE", "shadow")
    shadowed = [v.positioning for v in create_variants(bp, strategy)]
    assert shadowed == baseline


def test_shadow_decision_saved():
    bp = _mini_blueprint()
    decision = record_shadow_decision(
        blueprint=bp,
        production_order=["cloud_infrastructure", "platform_reliability"],
        run_id="run-shadow-1",
    )
    assert decision is not None
    assert decision.policy_version
    from resume_engine.learning.repository import get_default_repository

    saved = get_default_repository().list_online_decisions(limit=5)
    assert any(r["run_id"] == "run-shadow-1" for r in saved)


def test_shadow_prediction_records_policy_version():
    bp = _mini_blueprint()
    decision = record_shadow_decision(
        blueprint=bp,
        production_order=["cloud_infrastructure"],
        run_id="run-shadow-2",
    )
    assert decision is not None
    assert decision.policy_version == online_config.ONLINE_POLICY_VERSION
    assert decision.shadow_ranked_actions
    assert all(p.policy_version == online_config.ONLINE_POLICY_VERSION for p in decision.shadow_ranked_actions)


# ---------------------------------------------------------------------------
# Observations
# ---------------------------------------------------------------------------


def test_final_variant_observation_updates_policy():
    bp = _mini_blueprint()
    policy = RiverStrategyPolicy(seed=42)
    before = policy.observation_count
    eligible = list_eligible_positionings(bp)
    action = eligible[0]
    obs = observe_final_outcome(
        blueprint=bp,
        learning_record=_good_record(variant_positioning=action),
        policy=policy,
        persist_policy=False,
    )
    assert obs is not None
    assert obs["eligible"] is True
    assert policy.observation_count == before + 1


def test_rejected_variant_does_not_update_policy():
    bp = _mini_blueprint()
    policy = RiverStrategyPolicy(seed=42)
    before = policy.observation_count
    observe_final_outcome(
        blueprint=bp,
        learning_record=_good_record(passed=False, eligible_for_learning=False),
        policy=policy,
        persist_policy=False,
    )
    assert policy.observation_count == before


def test_pipeline_error_does_not_update_policy():
    bp = _mini_blueprint()
    policy = RiverStrategyPolicy(seed=42)
    before = policy.observation_count
    observe_final_outcome(
        blueprint=bp,
        learning_record=_good_record(status="PIPELINE_ERROR", passed=False),
        policy=policy,
        persist_policy=False,
    )
    assert policy.observation_count == before


# ---------------------------------------------------------------------------
# Persistence / fallback
# ---------------------------------------------------------------------------


def test_policy_store_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "resume_engine.learning.online.policy_store.ONLINE_LEARNING_STORAGE_DIR",
        tmp_path / "online",
    )
    policy = RiverStrategyPolicy(seed=7)
    ctx = build_context_features(_mini_blueprint())
    policy.observe(ctx, "cloud_infrastructure", 0.9)
    path = save_policy(policy)
    assert path.exists()
    loaded = load_policy(directory=tmp_path / "online")
    assert loaded is not None
    assert loaded.observation_count == 1


def test_corrupt_policy_falls_back_deterministically(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "resume_engine.learning.online.policy_store.ONLINE_LEARNING_STORAGE_DIR",
        tmp_path / "online",
    )
    d = policy_dir()
    (d / "policy.pkl").write_bytes(b"not-a-pickle")
    assert load_policy(directory=d) is None
    # Phase 2 still works via create_variants
    bp = get_blueprint("02_pure_devops")
    variants = create_variants(bp, build_strategy(bp))
    assert variants


def test_atomic_policy_save(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "resume_engine.learning.online.policy_store.ONLINE_LEARNING_STORAGE_DIR",
        tmp_path / "online",
    )
    policy = RiverStrategyPolicy(seed=1)
    save_policy(policy)
    policy.observe(build_context_features(_mini_blueprint()), "cloud_infrastructure", 0.5)
    save_policy(policy)
    assert (tmp_path / "online" / "policy.pkl").exists()
    assert (tmp_path / "online" / "policy.previous.pkl").exists()
    assert (tmp_path / "online" / "policy_metadata.json").exists()


def test_sqlite_policy_decision_roundtrip():
    bp = _mini_blueprint()
    record_shadow_decision(
        blueprint=bp,
        production_order=["cloud_infrastructure"],
        run_id="sql-dec-1",
    )
    from resume_engine.learning.repository import get_default_repository

    rows = get_default_repository().list_online_decisions()
    assert any(r["run_id"] == "sql-dec-1" for r in rows)
    assert any(r["policy_version"] for r in rows)


def test_sqlite_policy_observation_roundtrip():
    bp = _mini_blueprint()
    observe_final_outcome(
        blueprint=bp,
        learning_record=_good_record(run_id="sql-obs-1", variant_positioning="cloud_infrastructure"),
        policy=RiverStrategyPolicy(seed=1),
        persist_policy=False,
    )
    from resume_engine.learning.repository import get_default_repository

    rows = get_default_repository().list_online_observations()
    assert any(r["run_id"] == "sql-obs-1" for r in rows)


def test_replay_dry_run_does_not_mutate_policy():
    from resume_engine.learning.repository import get_default_repository

    repo = get_default_repository()
    # Incomplete historical row — skipped
    repo.save_outcome(_good_record(run_id="hist1", p1_count=None))
    policy = RiverStrategyPolicy(seed=3)
    before = policy.observation_count
    report = replay_from_repository(dry_run=True, policy=policy)
    assert report.dry_run is True
    assert policy.observation_count == before


def test_replay_skips_incomplete_historical_context():
    from resume_engine.learning.repository import get_default_repository

    repo = get_default_repository()
    repo.save_outcome(
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
            # missing primary_family/seniority → incomplete
        }
    )
    report = replay_from_repository(dry_run=True)
    assert report.usable_records == 0
    assert report.skipped_records >= 1


def test_online_failure_does_not_fail_phase2(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("forced online failure")

    monkeypatch.setattr(
        "resume_engine.learning.online.shadow_runner.build_context_features",
        boom,
    )
    bp = get_blueprint("02_pure_devops")
    variants = create_variants(bp, build_strategy(bp))
    assert len(variants) >= 1
    decision = record_shadow_decision(
        blueprint=bp,
        production_order=[v.positioning for v in variants],
        run_id="fail-soft",
    )
    assert decision is None
