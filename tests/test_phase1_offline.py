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
    if os.getenv("RUN_LIVE_TESTS") != "1":
        pytest.skip("LIVE_TEST_NOT_RUN: set RUN_LIVE_TESTS=1 with credentials to execute.")
    pytest.fail("Live Phase 1 harness not executed in this Wave 2 offline suite.")
