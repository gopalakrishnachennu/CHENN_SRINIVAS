"""
Phase 1 offline extraction / blueprint construction tests.

These do NOT call live OpenAI or Laya.
Live E2E is opt-in via RUN_LIVE_TESTS=1.
"""
from __future__ import annotations

import os

import pytest

from jd_blueprint_engine import placement_rules
from resume_engine.models.jd_blueprint import CertificationRequirement, JDBlueprint


def test_priority_p4_placement_is_optional_only():
    assert placement_rules("P4", "adjacent") == ["technical_skills_optional"]


def test_priority_p1_includes_summary_and_experience():
    sections = placement_rules("P1", "technology")
    assert "technical_skills" in sections
    assert "experience_responsibilities" in sections
    assert "professional_summary" in sections


def test_blueprint_certification_semantics_from_structured_payload():
    bp = JDBlueprint.model_validate(
        {
            "blueprint_version": "1.0",
            "jd_hash": "phase1_offline_cert",
            "created_at": "2026-09-22T00:00:00+00:00",
            "job": {
                "primary_family": "devops_cloud",
                "secondary_family": "none",
                "seniority": "senior",
                "hybrid_probability": 0.1,
            },
            "priority_skills": {"P1": ["AWS"], "P2": ["Terraform"], "P3": [], "P4": []},
            "entities": [
                {
                    "name": "AWS",
                    "category": "cloud",
                    "priority": "P1",
                    "source": "jd_direct",
                    "placement": ["technical_skills", "experience_responsibilities", "professional_summary"],
                }
            ],
            "responsibilities": ["Build cloud infrastructure"],
            "certifications": [
                {
                    "name": "AWS Certified Solutions Architect",
                    "requirement": "mandatory",
                    "evidence": "must have",
                    "source": "jd_direct",
                    "candidate_verified": False,
                }
            ],
            "generation_contract": {
                "allowed_technologies": ["AWS", "Terraform"],
                "allow_new_llm_skills": False,
                "allowed_sources": ["jd_direct", "approved_adjacent"],
            },
        }
    )
    assert isinstance(bp.certifications[0], CertificationRequirement)
    assert bp.certifications[0].requirement == "mandatory"
    assert bp.responsibility_entries()[0]["id"] == "R001"


@pytest.mark.live
def test_live_phase1_openai_laya_e2e_opt_in():
    """
    Opt-in live Phase 1 harness.

    Requires:
      RUN_LIVE_TESTS=1
      OPENAI_API_KEY set (non-placeholder)

    Without both, reports LIVE_TEST_NOT_RUN and skips (no paid spend).
    """
    from resume_engine.live.phase1_harness import preflight_live_harness, run_phase1_live_harness

    ok, reason = preflight_live_harness()
    if not ok:
        pytest.skip(reason)

    # Optional: SKIP_LAYA_LIVE=1 to avoid heavy local Laya download in CI-like live runs.
    skip_laya = os.getenv("SKIP_LAYA_LIVE", "").strip() == "1"
    result = run_phase1_live_harness(skip_laya=skip_laya)
    if skip_laya:
        assert result.status == "PASS_OPENAI_LAYA_SKIPPED", result.message
        assert result.openai_live == "PASS"
        assert result.laya_live == "SKIPPED"
        assert result.full_phase1_live_e2e == "SKIPPED"
    else:
        assert result.status == "PASS", result.message
        assert result.openai_live == "PASS"
        assert result.laya_live == "PASS"
        assert result.full_phase1_live_e2e == "PASS"
    assert result.blueprint_path
    assert result.default_registry_unchanged is True
    assert result.p1
    assert any("aws" in t.lower() for t in result.allowed_technologies)
