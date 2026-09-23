"""
Wave 2 P1 quality tests.

Covers dynamic variants, certifications, bullet provenance,
responsibility mapping, Laya batching, regeneration helpers,
cross-run uniqueness, and implementation audit honesty.
"""
from __future__ import annotations

import json

from resume_engine.config import thresholds
from resume_engine.generation.bullet_enrichment import (
    apply_certification_policy,
    attach_bullet_metadata,
)
from resume_engine.generation.provenance import attach_skill_provenance
from resume_engine.learning.fingerprint_store import (
    save_fingerprint,
    validate_cross_run_uniqueness,
)
from resume_engine.models.jd_blueprint import CertificationRequirement, JDBlueprint
from resume_engine.models.resume_schema import ResumeExperience, ResumeJSON
from resume_engine.models.resume_strategy import VariantStrategy
from resume_engine.reports.behavioral_audit import _good_resume, _monster_blueprint
from resume_engine.reports.implementation_audit import run_implementation_audit
from resume_engine.strategy.strategy_builder import build_strategy
from resume_engine.strategy.variant_planner import create_variants, select_angle_templates
from resume_engine.validation.laya_validator import validate_with_laya
from resume_engine.validation.responsibility_validator import validate_responsibilities
from resume_engine.validation.technology_firewall import validate_technology_firewall
from resume_engine.validation.variant_regeneration import (
    choose_weaker_variant,
    find_duplicate_pairs,
    variant_focus_score,
)
from tests.fixture_blueprint_builder import get_blueprint


def _resume_many_bullets(count: int = 25) -> ResumeJSON:
    bullets = [
        f"Delivered production platform work item {i} using AWS Terraform Kubernetes Python CI/CD."
        for i in range(count)
    ]
    return ResumeJSON(
        target_title="Senior Engineer",
        summary="Senior engineer focused on AWS Terraform Kubernetes Python CI/CD.",
        technical_skills={"Core": ["AWS", "Terraform", "Kubernetes", "Python", "CI/CD"]},
        experience=[ResumeExperience(company="A", title="Engineer", bullets=bullets)],
        projects=[],
        certifications=[],
        variant_id="V01",
    )


# ---------------------------------------------------------------------------
# Dynamic variants
# ---------------------------------------------------------------------------


def test_devops_variants():
    bp = get_blueprint("02_pure_devops")
    variants = create_variants(bp, build_strategy(bp))
    names = {v.positioning for v in variants}
    assert len(variants) == 5
    assert names & {
        "cloud_infrastructure",
        "automation_iac",
        "container_orchestration",
        "platform_reliability",
        "cloud_support",
    }
    assert "spark_databricks_platform" not in names
    assert "rag_integration" not in names


def test_data_engineering_variants():
    bp = get_blueprint("01_pure_data_engineer")
    names = {v.positioning for v in create_variants(bp, build_strategy(bp))}
    assert "pipeline_engineering" in names or "spark_databricks_platform" in names
    assert "networking_support" not in names


def test_ai_variants():
    bp = get_blueprint("05_ai_engineer_openai_claude")
    names = {v.positioning for v in create_variants(bp, build_strategy(bp))}
    assert any("ai" in name or "llm" in name or "rag" in name or "model" in name for name in names)


def test_data_analytics_variants():
    # Construct analytics-focused blueprint from analytics family fixture if present,
    # else synthesize via monster with analytics primary.
    bp = _monster_blueprint()
    bp.job.primary_family = "data_analytics"
    bp.job.secondary_family = "none"
    bp.job.hybrid_probability = 0.1
    bp.priority_skills = {
        "P1": ["SQL", "Tableau"],
        "P2": ["Python", "Power BI"],
        "P3": ["dbt"],
        "P4": [],
    }
    bp.generation_contract.allowed_technologies = ["SQL", "Tableau", "Python", "Power BI", "dbt"]
    bp.responsibilities = ["Build dashboards", "Deliver SQL analytics", "Automate reporting"]
    names = {v.positioning for v in create_variants(bp, build_strategy(bp))}
    assert names & {"sql_analytics", "bi_dashboard", "business_insights", "analytics_automation", "data_quality_analytics"}
    assert "spark_databricks_platform" not in names


def test_test_engineering_variants():
    bp = _monster_blueprint()
    bp.job.primary_family = "test_engineering"
    bp.job.secondary_family = "none"
    bp.job.hybrid_probability = 0.05
    bp.priority_skills = {"P1": ["Python", "CI/CD"], "P2": ["Docker"], "P3": [], "P4": []}
    bp.generation_contract.allowed_technologies = ["Python", "CI/CD", "Docker"]
    bp.responsibilities = ["Automate tests", "Validate systems", "Analyze failures"]
    bp.domain_terms = ["test automation", "systems validation", "failure analysis"]
    names = {v.positioning for v in create_variants(bp, build_strategy(bp))}
    assert names & {
        "test_automation",
        "systems_validation",
        "failure_analysis",
        "test_infrastructure",
        "manufacturing_test",
    }


def test_support_variants():
    bp = _monster_blueprint()
    bp.job.primary_family = "infrastructure_support"
    bp.job.secondary_family = "none"
    bp.job.hybrid_probability = 0.05
    bp.priority_skills = {"P1": ["Linux", "AWS"], "P2": ["Python"], "P3": [], "P4": []}
    bp.generation_contract.allowed_technologies = ["Linux", "AWS", "Python"]
    bp.responsibilities = ["Support servers", "Respond to incidents", "Automate runbooks"]
    bp.domain_terms = ["systems operations", "cloud support", "reliability"]
    names = {v.positioning for v in create_variants(bp, build_strategy(bp))}
    assert names & {
        "systems_operations",
        "cloud_support",
        "reliability_support",
        "support_automation",
        "networking_support",
    }


def test_hybrid_variants_preserve_both_families():
    bp = _monster_blueprint()
    variants = create_variants(bp, build_strategy(bp))
    families = set()
    for angle in select_angle_templates(bp):
        families.update(angle.families)
    assert "devops_cloud" in families
    assert "data_engineering" in families or any(
        "data" in v.positioning or "spark" in v.positioning or "pipeline" in v.positioning
        for v in variants
    )


def test_no_unrelated_variant_created():
    bp = get_blueprint("02_pure_devops")
    names = {v.positioning for v in create_variants(bp, build_strategy(bp))}
    unrelated = {"rag_integration", "bi_dashboard", "manufacturing_test", "sql_analytics"}
    assert not (names & unrelated)


# ---------------------------------------------------------------------------
# Certifications
# ---------------------------------------------------------------------------


def test_mandatory_certification_preserved():
    bp = get_blueprint("13_mandatory_certification")
    assert any(c.name == "AWS Certified Solutions Architect" and c.requirement == "mandatory" for c in bp.certifications)


def test_preferred_certification_preserved():
    bp = get_blueprint("14_preferred_certification")
    assert any(
        c.name == "Databricks Data Engineer Associate" and c.requirement == "preferred"
        for c in bp.certifications
    )


def test_template_does_not_claim_unverified_cert():
    bp = get_blueprint("13_mandatory_certification")
    resume = ResumeJSON(
        target_title="Engineer",
        summary="Cloud engineer",
        technical_skills={"Cloud": ["AWS"]},
        experience=[],
        certifications=["AWS Certified Solutions Architect"],
    )
    resume = apply_certification_policy(bp, resume, generation_mode="TEMPLATE")
    assert resume.certifications == []
    assert resume.certification_records
    assert all(r.status in {"recommended", "jd_requirement"} for r in resume.certification_records)
    assert all(not r.candidate_verified for r in resume.certification_records)


def test_candidate_mode_only_uses_verified_cert():
    bp = get_blueprint("13_mandatory_certification")
    resume = ResumeJSON(
        target_title="Engineer",
        summary="Cloud engineer",
        technical_skills={"Cloud": ["AWS"]},
        experience=[],
        certifications=["AWS Certified Solutions Architect", "Fake Cert"],
    )
    resume = apply_certification_policy(
        bp,
        resume,
        generation_mode="CANDIDATE",
        candidate_profile={"certifications": [{"name": "AWS Certified Solutions Architect", "verified": True}]},
    )
    assert resume.certifications == ["AWS Certified Solutions Architect"]
    possessed = [r for r in resume.certification_records if r.status == "possessed"]
    assert len(possessed) == 1
    assert possessed[0].candidate_verified is True


# ---------------------------------------------------------------------------
# Bullet provenance / firewall / responsibility mapping
# ---------------------------------------------------------------------------


def test_unapproved_bullet_technology_blocked():
    bp = _monster_blueprint()
    resume = attach_skill_provenance(bp, _good_resume())
    resume = attach_bullet_metadata(bp, resume)
    resume.experience[0].bullet_meta[0].technologies.append("Salesforce")
    result = validate_technology_firewall(bp, resume)
    assert not result.passed
    assert any(i.code == "FAIL_UNAPPROVED_BULLET_TECHNOLOGY" for i in result.issues)


def test_approved_unknown_jd_tool_allowed():
    bp = _monster_blueprint()
    resume = attach_skill_provenance(bp, _good_resume())
    resume = attach_bullet_metadata(bp, resume)
    # Databricks is allowed / JD-direct
    assert "Databricks" in resume.experience[0].bullet_meta[0].technologies or any(
        "Databricks" in b.technologies for exp in resume.experience for b in exp.bullet_meta
    )
    result = validate_technology_firewall(bp, resume)
    assert result.passed


def test_llm_generated_tool_blocked():
    bp = _monster_blueprint()
    resume = attach_skill_provenance(bp, _good_resume())
    resume.technical_skills.setdefault("Extra", []).append("MadeUpToolX")
    resume = attach_skill_provenance(bp, resume)
    result = validate_technology_firewall(bp, resume)
    assert not result.passed
    assert any(i.code in {"FAIL_LLM_GENERATED_TECHNOLOGY", "FAIL_UNAPPROVED_TECHNOLOGY"} for i in result.issues)


def test_provenance_survives_repair():
    bp = _monster_blueprint()
    resume = attach_skill_provenance(bp, _good_resume())
    resume = attach_bullet_metadata(bp, resume)
    before_ids = [b.id for exp in resume.experience for b in exp.bullet_meta]
    # Simulate repair rewriting one bullet text then re-enriching.
    resume.experience[0].bullets[0] = (
        "Owned Databricks Terraform AWS Kubernetes OpenAI API Claude API platform delivery with CI/CD Python Spark."
    )
    resume = attach_bullet_metadata(bp, resume)
    after_ids = [b.id for exp in resume.experience for b in exp.bullet_meta]
    assert before_ids == after_ids
    assert resume.experience[0].bullet_meta[0].id == "EXP_0_BULLET_0"


def test_responsibility_mapping_report_present():
    bp = _monster_blueprint()
    resume = attach_bullet_metadata(bp, attach_skill_provenance(bp, _good_resume()))
    result = validate_responsibilities(bp, resume)
    assert "responsibility_mapping" in result.details
    assert result.details["mapping_report"]
    assert any(line.startswith("R001") for line in result.details["mapping_report"])


# ---------------------------------------------------------------------------
# Laya batching
# ---------------------------------------------------------------------------


class _FakeLaya:
    def __init__(self, fail_batches: set[int] | None = None):
        self.calls = []
        self.fail_batches = fail_batches or set()

    def predict(self, state, questions):
        self.calls.append(questions)
        batch_index = len(self.calls)
        if batch_index in self.fail_batches:
            raise RuntimeError("simulated laya failure")
        answers = {}
        for key in questions:
            answers[key] = {"noul": 0.85}
        return {"answers": answers}


def test_more_than_20_bullets_all_validated():
    bp = _monster_blueprint()
    resume = _resume_many_bullets(25)
    agent = _FakeLaya()
    result = validate_with_laya(bp, resume, agent)
    assert result.details["validated_bullet_count"] == 25
    assert result.details["total_bullet_count"] == 25
    assert result.passed


def test_batch_counts_correct():
    bp = _monster_blueprint()
    resume = _resume_many_bullets(25)
    agent = _FakeLaya()
    result = validate_with_laya(bp, resume, agent)
    expected_batches = (25 + thresholds.LAYA_BULLET_BATCH_SIZE - 1) // thresholds.LAYA_BULLET_BATCH_SIZE
    assert result.details["batch_count"] == expected_batches
    assert len(agent.calls) == expected_batches


def test_failed_batch_not_silent_pass():
    bp = _monster_blueprint()
    resume = _resume_many_bullets(12)

    class _AlwaysFailLaya:
        def predict(self, state, questions):
            raise RuntimeError("simulated permanent laya failure")

    result = validate_with_laya(bp, resume, _AlwaysFailLaya())
    assert not result.passed
    assert any(i.code == "FAIL_LAYA_BATCH" for i in result.issues)
    assert result.details.get("failed_batch") is True


# ---------------------------------------------------------------------------
# Variant regeneration helpers
# ---------------------------------------------------------------------------


def test_duplicate_variant_regenerates_weaker_only():
    left = _good_resume("V01", "cloud platform")
    right = _good_resume("V02", "cloud platform")
    left_variant = VariantStrategy(variant_id="V01", positioning="cloud_infrastructure", description="x")
    right_variant = VariantStrategy(variant_id="V02", positioning="cloud_infrastructure", description="x")
    pairs = find_duplicate_pairs(
        [left, right],
        {"V01": 90.0, "V02": 80.0},
        {"V01": left_variant, "V02": right_variant},
        threshold=0.50,
    )
    assert pairs
    assert pairs[0]["weaker_variant_id"] == "V02"


def test_valid_variants_not_regenerated():
    left = _good_resume("V01", "cloud platform")
    right = _good_resume("V02", "Databricks platform")
    pairs = find_duplicate_pairs(
        [left, right],
        {"V01": 95.0, "V02": 96.0},
        threshold=0.99,
    )
    assert pairs == []


def test_regeneration_retry_limit():
    assert thresholds.VARIANT_REGEN_MAX == 2
    weaker = choose_weaker_variant(
        _good_resume("V01"),
        _good_resume("V02"),
        70.0,
        90.0,
    )
    assert weaker == "V01"


def test_variant_focus_score_prefers_angle_terms():
    variant = VariantStrategy(
        variant_id="V01",
        positioning="spark_databricks_platform",
        description="x",
        emphasis={"Databricks": 1.0, "Apache Spark": 0.95, "Python": 0.9},
    )
    resume = _good_resume("V01", "Databricks platform")
    score = variant_focus_score(resume, variant)
    assert score > 0


# ---------------------------------------------------------------------------
# Cross-run uniqueness
# ---------------------------------------------------------------------------


def test_cross_run_duplication_detected(tmp_path, monkeypatch):
    from resume_engine.learning import fingerprint_store
    from resume_engine.learning.repository import (
        LearningRepository,
        reset_default_repository_for_tests,
    )

    monkeypatch.setattr(fingerprint_store, "FINGERPRINTS_FILE", tmp_path / "fps.jsonl")
    reset_default_repository_for_tests(
        LearningRepository(db_path=tmp_path / "fps.sqlite3", dual_write_jsonl=True)
    )
    bp = _monster_blueprint()
    resume = _good_resume("V01")
    save_fingerprint(jd_hash=bp.jd_hash, run_id="run-old", variant_id="V01", resume=resume, passed=True)
    result = validate_cross_run_uniqueness(resume, bp.jd_hash, run_id="run-new", threshold=0.5)
    assert not result.passed
    assert any(i.code == "FAIL_CROSS_RUN_DUPLICATION" for i in result.issues)
    reset_default_repository_for_tests(None)


def test_cross_run_different_content_passes(tmp_path, monkeypatch):
    from resume_engine.learning import fingerprint_store
    from resume_engine.learning.repository import (
        LearningRepository,
        reset_default_repository_for_tests,
    )

    monkeypatch.setattr(fingerprint_store, "FINGERPRINTS_FILE", tmp_path / "fps.jsonl")
    reset_default_repository_for_tests(
        LearningRepository(db_path=tmp_path / "fps.sqlite3", dual_write_jsonl=True)
    )
    bp = _monster_blueprint()
    prior = _good_resume("V01", "cloud platform")
    current = _good_resume("V02", "AI-enabled data platform")
    current.summary = "Completely different narrative for uniqueness testing with Databricks Terraform."
    save_fingerprint(jd_hash=bp.jd_hash, run_id="run-old", variant_id="V01", resume=prior, passed=True)
    result = validate_cross_run_uniqueness(current, bp.jd_hash, run_id="run-new", threshold=0.98)
    assert result.passed
    reset_default_repository_for_tests(None)


# ---------------------------------------------------------------------------
# Implementation audit honesty
# ---------------------------------------------------------------------------


def test_implementation_audit_does_not_mark_import_as_tested():
    audit = run_implementation_audit()
    assert audit.modules
    for status in audit.modules.values():
        assert status.tested is False
        assert status.live_test_status == "LIVE_TEST_NOT_RUN"
        payload = json.loads(status.details)
        assert "imports_successfully" in payload
        assert payload.get("unit_test_passed") is None


def test_string_cert_coercion_backward_compatible():
    bp = JDBlueprint.model_validate(
        {
            "blueprint_version": "1.0",
            "jd_hash": "x",
            "created_at": "2026-09-22T00:00:00+00:00",
            "job": {
                "primary_family": "devops_cloud",
                "secondary_family": "none",
                "seniority": "senior",
                "hybrid_probability": 0.1,
            },
            "priority_skills": {"P1": ["AWS"], "P2": [], "P3": [], "P4": []},
            "entities": [],
            "responsibilities": ["Manage AWS"],
            "certifications": ["AWS Certified Solutions Architect"],
            "generation_contract": {"allowed_technologies": ["AWS"]},
        }
    )
    assert isinstance(bp.certifications[0], CertificationRequirement)
    assert bp.certification_names() == ["AWS Certified Solutions Architect"]
