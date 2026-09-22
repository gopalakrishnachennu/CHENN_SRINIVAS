"""
test_behavioral_fixtures.py — Phase 2.5 behavioral validation test suite.

Tests each of the 15 JD fixtures against their expected assertions:
  - Blueprint structure assertions
  - Critical skill detection
  - Hybrid-family detection and retention
  - AI tool placement (P1/P2 tools must appear in skills + experience)
  - Technology firewall (unauthorized tools are hard-blocked)
  - Duplicate bullet detection
  - Targeted repair (only failing parts are flagged)
  - Variant diversity (too-similar pairs are flagged)

All tests run deterministically — NO live OpenAI calls required.
"""
from __future__ import annotations

import pytest

from resume_engine.generation.provenance import attach_skill_provenance
from resume_engine.repair.repair_planner import build_repair_plan
from resume_engine.validation.ai_tool_placement_validator import validate_ai_tool_placement
from resume_engine.validation.ats_validator import validate_ats
from resume_engine.validation.coverage_validator import validate_coverage
from resume_engine.validation.duplicate_validator import validate_duplicates
from resume_engine.validation.hybrid_family_validator import validate_hybrid_family_retention
from resume_engine.validation.role_drift_validator import validate_role_drift
from resume_engine.validation.technology_firewall import validate_technology_firewall
from resume_engine.validation.variant_similarity_validator import validate_variant_similarity

from tests.fixture_blueprint_builder import get_blueprint, load_assertions, all_fixture_ids
from tests.fixture_resume_builder import (
    good_resume_for,
    bad_resume_missing_p1,
    bad_resume_with_hallucination,
    bad_resume_with_duplicates,
    bad_resume_missing_ai_tools,
    bad_resume_wrong_family,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

AI_HINTS = {"openai", "claude", "anthropic", "langchain", "langgraph", "bedrock", "vertex", "mosaic"}


def _has_ai_tools(blueprint_id: str, assertions: dict) -> bool:
    a = assertions.get(blueprint_id, {})
    return bool(a.get("ai_tools_requiring_responsibility"))


def _ai_tools(blueprint_id: str, assertions: dict) -> list[str]:
    return assertions.get(blueprint_id, {}).get("ai_tools_requiring_responsibility", [])


def _is_hybrid(blueprint_id: str, assertions: dict) -> bool:
    return assertions.get(blueprint_id, {}).get("hybrid_expected", False)


# ---------------------------------------------------------------------------
# Meta: fixture inventory
# ---------------------------------------------------------------------------

class TestFixtureInventory:
    """Verify the fixture setup itself is complete."""

    def test_15_fixture_jd_files_exist(self):
        from pathlib import Path
        fixture_dir = Path(__file__).parent / "fixtures" / "jds"
        files = list(fixture_dir.glob("*.txt"))
        assert len(files) == 15, f"Expected 15 JD fixture files, found {len(files)}"

    def test_all_fixtures_have_assertions(self):
        assertions = load_assertions()
        fixture_ids = all_fixture_ids()
        missing = [fid for fid in fixture_ids if fid not in assertions]
        assert not missing, f"Fixtures missing assertions: {missing}"

    def test_all_fixtures_have_blueprints(self):
        for fixture_id in all_fixture_ids():
            bp = get_blueprint(fixture_id)
            assert bp is not None
            assert bp.jd_hash == fixture_id or bp.jd_hash.startswith(fixture_id[:10])

    def test_assertion_count_equals_fixture_count(self):
        assertions = load_assertions()
        fixture_ids = all_fixture_ids()
        assert len(assertions) >= len(fixture_ids), (
            f"Assertion count {len(assertions)} < fixture count {len(fixture_ids)}"
        )


# ---------------------------------------------------------------------------
# Parametrized: Blueprint assertions for all 15 fixtures
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fixture_id", all_fixture_ids())
class TestBlueprintAssertions:
    """Verify blueprint structure matches expected assertions for every fixture."""

    def test_primary_family(self, fixture_id):
        assertions = load_assertions()
        blueprint = get_blueprint(fixture_id)
        expected = assertions[fixture_id]["expected_primary_family"]
        assert blueprint.job.primary_family == expected, (
            f"[{fixture_id}] primary_family: got {blueprint.job.primary_family!r}, want {expected!r}"
        )

    def test_secondary_family(self, fixture_id):
        assertions = load_assertions()
        blueprint = get_blueprint(fixture_id)
        expected = assertions[fixture_id]["expected_secondary_family"]
        assert blueprint.job.secondary_family == expected, (
            f"[{fixture_id}] secondary_family: got {blueprint.job.secondary_family!r}, want {expected!r}"
        )

    def test_hybrid_detection(self, fixture_id):
        assertions = load_assertions()
        blueprint = get_blueprint(fixture_id)
        expected_hybrid = assertions[fixture_id]["hybrid_expected"]
        actual_hybrid = (
            blueprint.job.hybrid_probability >= 0.55
            and blueprint.job.secondary_family != "none"
        )
        assert actual_hybrid == expected_hybrid, (
            f"[{fixture_id}] hybrid: expected {expected_hybrid}, "
            f"got prob={blueprint.job.hybrid_probability}, secondary={blueprint.job.secondary_family}"
        )

    def test_critical_skills_in_blueprint(self, fixture_id):
        assertions = load_assertions()
        blueprint = get_blueprint(fixture_id)
        critical = assertions[fixture_id].get("critical_skills", [])
        all_blueprint_skills = [
            skill
            for skills in blueprint.priority_skills.values()
            for skill in skills
        ]
        for skill in critical:
            assert skill in all_blueprint_skills, (
                f"[{fixture_id}] critical skill {skill!r} not in blueprint skills: {all_blueprint_skills}"
            )

    def test_has_p1_skills(self, fixture_id):
        blueprint = get_blueprint(fixture_id)
        assert len(blueprint.priority_skills.get("P1", [])) >= 1, (
            f"[{fixture_id}] must have at least 1 P1 skill"
        )

    def test_has_responsibilities(self, fixture_id):
        blueprint = get_blueprint(fixture_id)
        assert len(blueprint.responsibilities) >= 1, (
            f"[{fixture_id}] must have at least 1 responsibility"
        )

    def test_generation_contract_populated(self, fixture_id):
        blueprint = get_blueprint(fixture_id)
        assert len(blueprint.generation_contract.allowed_technologies) >= 1, (
            f"[{fixture_id}] generation_contract.allowed_technologies must not be empty"
        )

    def test_mandatory_certifications_in_blueprint(self, fixture_id):
        assertions = load_assertions()
        blueprint = get_blueprint(fixture_id)
        mandatory = assertions[fixture_id].get("mandatory_certifications", [])
        for cert in mandatory:
            assert cert in blueprint.certifications, (
                f"[{fixture_id}] mandatory cert {cert!r} not in blueprint.certifications"
            )

    def test_preferred_certifications_in_blueprint(self, fixture_id):
        assertions = load_assertions()
        blueprint = get_blueprint(fixture_id)
        preferred = assertions[fixture_id].get("preferred_certifications", [])
        for cert in preferred:
            assert cert in blueprint.certifications, (
                f"[{fixture_id}] preferred cert {cert!r} not in blueprint.certifications"
            )


# ---------------------------------------------------------------------------
# Coverage Validator — good resumes should pass
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fixture_id", all_fixture_ids())
class TestCoverageValidator:
    """Good resumes must pass P1 coverage; bad ones must fail."""

    def test_good_resume_passes_p1_coverage(self, fixture_id):
        blueprint = get_blueprint(fixture_id)
        resume = attach_skill_provenance(blueprint, good_resume_for(blueprint))
        result = validate_coverage(blueprint, resume)
        p1_coverage = result.details.get("P1_coverage", 0.0)
        assert p1_coverage == 1.0, (
            f"[{fixture_id}] P1 coverage: {p1_coverage:.0%}. "
            f"Missing: {result.details.get('P1_missing')}"
        )

    def test_bad_resume_fails_p1_coverage(self, fixture_id):
        blueprint = get_blueprint(fixture_id)
        p1 = blueprint.priority_skills.get("P1", [])
        if len(p1) <= 1:
            pytest.skip(f"[{fixture_id}] only 1 P1 skill — can't create useful missing-P1 resume")
        bad = bad_resume_missing_p1(blueprint)
        result = validate_coverage(blueprint, bad)
        # Must fail or have some P1 missing
        p1_coverage = result.details.get("P1_coverage", 1.0)
        assert p1_coverage < 1.0, (
            f"[{fixture_id}] Expected bad resume to fail P1 coverage but got {p1_coverage:.0%}"
        )


# ---------------------------------------------------------------------------
# Technology Firewall — hallucination must be hard-blocked
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fixture_id", all_fixture_ids())
class TestTechnologyFirewall:
    """Unauthorized technologies must produce FAIL_UNAPPROVED_TECHNOLOGY errors."""

    def test_good_resume_passes_firewall(self, fixture_id):
        blueprint = get_blueprint(fixture_id)
        resume = attach_skill_provenance(blueprint, good_resume_for(blueprint))
        result = validate_technology_firewall(blueprint, resume)
        assert result.passed, (
            f"[{fixture_id}] Good resume failed firewall: "
            f"{[i.message for i in result.issues]}"
        )

    def test_hallucinated_resume_fails_firewall(self, fixture_id):
        blueprint = get_blueprint(fixture_id)
        # Only run this test if Salesforce is not in the blueprint's allowed list
        allowed = {t.lower() for t in blueprint.generation_contract.allowed_technologies}
        if "salesforce" in allowed:
            pytest.skip(f"[{fixture_id}] Salesforce is allowed — skipping hallucination test")
        bad = bad_resume_with_hallucination(blueprint)
        result = validate_technology_firewall(blueprint, bad)
        assert not result.passed, (
            f"[{fixture_id}] Hallucinated resume should have failed firewall but passed"
        )
        error_codes = [i.code for i in result.issues if i.severity == "error"]
        assert any("UNAPPROVED" in c for c in error_codes), (
            f"[{fixture_id}] Expected FAIL_UNAPPROVED_TECHNOLOGY, got: {error_codes}"
        )

    def test_unauthorized_count_is_zero_for_good_resume(self, fixture_id):
        blueprint = get_blueprint(fixture_id)
        resume = attach_skill_provenance(blueprint, good_resume_for(blueprint))
        result = validate_technology_firewall(blueprint, resume)
        assert result.details.get("unauthorized_count", 0) == 0, (
            f"[{fixture_id}] unauthorized_count={result.details.get('unauthorized_count')}"
        )


# ---------------------------------------------------------------------------
# AI Tool Placement Validator — P1/P2 AI tools must be in skills + experience
# ---------------------------------------------------------------------------

AI_FIXTURE_IDS = [
    fid for fid in all_fixture_ids()
    if any(
        any(h in s.lower() for h in AI_HINTS)
        for s in get_blueprint(fid).priority_skills.get("P1", [])
        + get_blueprint(fid).priority_skills.get("P2", [])
    )
]

NON_AI_FIXTURE_IDS = [fid for fid in all_fixture_ids() if fid not in AI_FIXTURE_IDS]


@pytest.mark.parametrize("fixture_id", AI_FIXTURE_IDS)
class TestAIToolPlacementValidator:
    """AI tools at P1/P2 must appear in both technical_skills AND experience bullets."""

    def test_good_resume_passes_ai_placement(self, fixture_id):
        blueprint = get_blueprint(fixture_id)
        resume = attach_skill_provenance(blueprint, good_resume_for(blueprint))
        result = validate_ai_tool_placement(blueprint, resume)
        errors = [i for i in result.issues if i.severity == "error"]
        assert not errors, (
            f"[{fixture_id}] AI placement errors: {[i.message for i in errors]}"
        )

    def test_bad_resume_missing_ai_fails_placement(self, fixture_id):
        blueprint = get_blueprint(fixture_id)
        assertions = load_assertions()
        ai_tools = _ai_tools(fixture_id, assertions)
        # If the fixture has no explicit "ai_tools_requiring_responsibility",
        # we still check if P1 AI tools exist in the blueprint
        if not ai_tools:
            p1_ai = [
                s for s in blueprint.priority_skills.get("P1", [])
                if any(h in s.lower() for h in AI_HINTS)
            ]
            if not p1_ai:
                pytest.skip(f"[{fixture_id}] No P1 AI tools with responsibility requirement")
            ai_tools = p1_ai
        bad = bad_resume_missing_ai_tools(blueprint)
        result = validate_ai_tool_placement(blueprint, bad)
        # Check that AI tools that are P1 in the blueprint are flagged
        p1_ai_in_blueprint = [
            s for s in blueprint.priority_skills.get("P1", [])
            if any(h in s.lower() for h in AI_HINTS)
        ]
        if not p1_ai_in_blueprint:
            # Only P2 AI tools — check that they appear in the bad resume's missing
            # The bad_resume_missing_ai_tools deliberately removes AI tools from skills+exp
            errors = [i for i in result.issues if i.severity == "error"]
            assert errors, (
                f"[{fixture_id}] Expected AI placement errors for resume missing P2 AI tools"
            )
        else:
            errors = [i for i in result.issues if i.severity == "error"]
            assert errors, (
                f"[{fixture_id}] Expected AI placement errors for resume missing P1 AI tools"
            )

    def test_p1_ai_tools_appear_in_skills(self, fixture_id):
        blueprint = get_blueprint(fixture_id)
        resume = attach_skill_provenance(blueprint, good_resume_for(blueprint))
        all_skills = [s for group in resume.technical_skills.values() for s in group]
        p1_ai_tools = [
            s for s in blueprint.priority_skills.get("P1", [])
            if any(h in s.lower() for h in AI_HINTS)
        ]
        for tool in p1_ai_tools:
            assert tool in all_skills, (
                f"[{fixture_id}] P1 AI tool {tool!r} not found in technical_skills: {all_skills}"
            )

    def test_p1_ai_tools_appear_in_experience(self, fixture_id):
        blueprint = get_blueprint(fixture_id)
        resume = attach_skill_provenance(blueprint, good_resume_for(blueprint))
        experience_text = " ".join(b for exp in resume.experience for b in exp.bullets)
        p1_ai_tools = [
            s for s in blueprint.priority_skills.get("P1", [])
            if any(h in s.lower() for h in AI_HINTS)
        ]
        for tool in p1_ai_tools:
            assert tool in experience_text, (
                f"[{fixture_id}] P1 AI tool {tool!r} not found in experience bullets"
            )


# ---------------------------------------------------------------------------
# Hybrid Family Validator — secondary family must be retained
# ---------------------------------------------------------------------------

HYBRID_FIXTURE_IDS = [fid for fid in all_fixture_ids() if _is_hybrid(fid, load_assertions())]
NON_HYBRID_FIXTURE_IDS = [fid for fid in all_fixture_ids() if not _is_hybrid(fid, load_assertions())]


@pytest.mark.parametrize("fixture_id", HYBRID_FIXTURE_IDS)
class TestHybridFamilyValidatorHybrid:
    """For hybrid JDs: both primary and secondary families must be in the resume."""

    def test_good_resume_passes_hybrid_validator(self, fixture_id):
        blueprint = get_blueprint(fixture_id)
        resume = attach_skill_provenance(blueprint, good_resume_for(blueprint))
        result = validate_hybrid_family_retention(blueprint, resume)
        assert result.passed, (
            f"[{fixture_id}] Hybrid validator failed on good resume: "
            f"{[i.message for i in result.issues]}"
        )

    def test_hybrid_is_detected(self, fixture_id):
        blueprint = get_blueprint(fixture_id)
        result = validate_hybrid_family_retention(blueprint, good_resume_for(blueprint))
        assert result.details.get("hybrid_expected") is True, (
            f"[{fixture_id}] hybrid_expected should be True"
        )

    def test_primary_family_represented(self, fixture_id):
        blueprint = get_blueprint(fixture_id)
        resume = attach_skill_provenance(blueprint, good_resume_for(blueprint))
        result = validate_hybrid_family_retention(blueprint, resume)
        assert result.details.get("primary_represented") is True, (
            f"[{fixture_id}] primary family not represented"
        )

    def test_secondary_family_retained(self, fixture_id):
        blueprint = get_blueprint(fixture_id)
        resume = attach_skill_provenance(blueprint, good_resume_for(blueprint))
        result = validate_hybrid_family_retention(blueprint, resume)
        assert result.details.get("secondary_represented") is True, (
            f"[{fixture_id}] secondary family not retained"
        )

    def test_unrelated_family_blocked(self, fixture_id):
        blueprint = get_blueprint(fixture_id)
        bad = bad_resume_wrong_family(blueprint)
        result = validate_hybrid_family_retention(blueprint, bad)
        unrelated = result.details.get("unrelated_terms", [])
        assert unrelated or not result.passed, (
            f"[{fixture_id}] Unrelated family should have been flagged"
        )


@pytest.mark.parametrize("fixture_id", NON_HYBRID_FIXTURE_IDS)
class TestHybridFamilyValidatorNonHybrid:
    """For non-hybrid JDs: validator should pass without secondary family pressure."""

    def test_good_resume_passes_hybrid_validator(self, fixture_id):
        blueprint = get_blueprint(fixture_id)
        # Sparse/generic JDs with unknown primary family ('other') cannot
        # be meaningfully validated for family representation — skip gracefully.
        if blueprint.job.primary_family == "other":
            pytest.skip(f"[{fixture_id}] primary_family='other' — family terms not defined")
        resume = attach_skill_provenance(blueprint, good_resume_for(blueprint))
        result = validate_hybrid_family_retention(blueprint, resume)
        assert result.passed, (
            f"[{fixture_id}] Non-hybrid validator failed: "
            f"{[i.message for i in result.issues]}"
        )


# ---------------------------------------------------------------------------
# Duplicate Bullet Validator
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fixture_id", all_fixture_ids())
class TestDuplicateValidator:

    def test_good_resume_passes_duplicate_check(self, fixture_id):
        blueprint = get_blueprint(fixture_id)
        resume = attach_skill_provenance(blueprint, good_resume_for(blueprint))
        result = validate_duplicates(resume)
        errors = [i for i in result.issues if i.severity == "error"]
        assert not errors, (
            f"[{fixture_id}] Good resume has duplicate errors: {[i.message for i in errors]}"
        )

    def test_duplicate_resume_fails_check(self, fixture_id):
        blueprint = get_blueprint(fixture_id)
        bad = bad_resume_with_duplicates(blueprint)
        result = validate_duplicates(bad)
        assert not result.passed, (
            f"[{fixture_id}] Duplicate resume should have failed duplicate check"
        )


# ---------------------------------------------------------------------------
# ATS Structure Validator
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fixture_id", all_fixture_ids())
class TestATSValidator:

    def test_good_resume_passes_ats(self, fixture_id):
        blueprint = get_blueprint(fixture_id)
        resume = attach_skill_provenance(blueprint, good_resume_for(blueprint))
        result = validate_ats(resume)
        # ATS warnings are acceptable, but no hard errors
        errors = [i for i in result.issues if i.severity == "error"]
        assert not errors, (
            f"[{fixture_id}] ATS hard errors: {[i.message for i in errors]}"
        )


# ---------------------------------------------------------------------------
# Role Drift Validator
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fixture_id", all_fixture_ids())
class TestRoleDriftValidator:

    def test_good_resume_no_role_drift(self, fixture_id):
        blueprint = get_blueprint(fixture_id)
        resume = attach_skill_provenance(blueprint, good_resume_for(blueprint))
        result = validate_role_drift(blueprint, resume)
        drift_errors = [i for i in result.issues if i.code == "FAIL_ROLE_DRIFT"]
        assert not drift_errors, (
            f"[{fixture_id}] Role drift detected in good resume: "
            f"{[i.message for i in drift_errors]}"
        )


# ---------------------------------------------------------------------------
# Targeted Repair — only failing parts should be flagged
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fixture_id", all_fixture_ids())
class TestTargetedRepairPlanner:

    def test_good_resume_has_no_critical_repair_required(self, fixture_id):
        """
        Good resumes should produce zero error-severity issues.
        P3 coverage warnings (e.g. Airflow, LangChain in P3 placement)
        are acceptable and do not constitute a critical repair need.
        """
        blueprint = get_blueprint(fixture_id)
        resume = attach_skill_provenance(blueprint, good_resume_for(blueprint))
        from resume_engine.models.validation_schema import ValidationBundle
        cov_result = validate_coverage(blueprint, resume)
        fw_result = validate_technology_firewall(blueprint, resume)
        dup_result = validate_duplicates(resume)
        bundle = ValidationBundle(
            variant_id="V01",
            resume_id=f"{fixture_id}_good",
            passed=True,
            optimization_score=95.0,
            action="PASS",
            validator_results=[cov_result, fw_result, dup_result],
        )
        plan = build_repair_plan(bundle)
        # Only error-severity issues should drive critical repair
        all_error_issues = [
            issue
            for result in [cov_result, fw_result, dup_result]
            for issue in result.issues
            if issue.severity == "error"
        ]
        assert not all_error_issues, (
            f"[{fixture_id}] Good resume has ERROR-severity issues triggering repair: "
            f"{[i.message for i in all_error_issues]}"
        )

    def test_bad_resume_generates_targeted_repair_plan(self, fixture_id):
        blueprint = get_blueprint(fixture_id)
        p1 = blueprint.priority_skills.get("P1", [])
        if len(p1) <= 1:
            pytest.skip(f"[{fixture_id}] too few P1 skills for repair test")
        bad = bad_resume_missing_p1(blueprint)
        from resume_engine.models.validation_schema import ValidationBundle
        cov_result = validate_coverage(blueprint, bad)
        fw_result = validate_technology_firewall(blueprint, bad)
        bundle = ValidationBundle(
            variant_id="VBAD",
            resume_id=f"{fixture_id}_bad",
            passed=False,
            optimization_score=50.0,
            action="REPAIR_REQUIRED",
            validator_results=[cov_result, fw_result],
        )
        plan = build_repair_plan(bundle)
        assert plan["required"], (
            f"[{fixture_id}] Expected repair to be required but got: {plan}"
        )
        assert plan["issue_count"] > 0, (
            f"[{fixture_id}] Expected issue_count > 0 in repair plan: {plan}"
        )


# ---------------------------------------------------------------------------
# Variant Diversity Validator
# ---------------------------------------------------------------------------

class TestVariantSimilarityValidator:
    """Paraphrase pairs must be blocked; genuinely distinct variants must pass."""

    def test_identical_variants_blocked(self):
        from tests.fixture_blueprint_builder import blueprint_03_devops_databricks_ai
        blueprint = blueprint_03_devops_databricks_ai()
        from tests.fixture_resume_builder import good_resume_for
        resume = good_resume_for(blueprint, "V01")
        resume2 = good_resume_for(blueprint, "V02")
        # Two identical resumes should be flagged
        result = validate_variant_similarity([resume, resume2], threshold=0.90)
        assert not result.passed, "Identical variants should fail similarity check"
        codes = [i.code for i in result.issues]
        assert "FAIL_VARIANT_DUPLICATION" in codes

    def test_distinct_variants_pass(self):
        from tests.fixture_blueprint_builder import blueprint_03_devops_databricks_ai
        blueprint = blueprint_03_devops_databricks_ai()
        from resume_engine.generation.provenance import attach_skill_provenance
        from resume_engine.models.resume_schema import ResumeJSON

        # Build 5 meaningfully different resumes with distinct bullets
        variant_angles = [
            ("V01", "cloud infrastructure automation", "Managed Terraform and AWS infrastructure."),
            ("V02", "Databricks data platform", "Owned Databricks workspace reliability."),
            ("V03", "AI-enabled deployment", "Built OpenAI API deployment checks."),
            ("V04", "Kubernetes operations", "Operated Kubernetes clusters with Helm."),
            ("V05", "data engineering pipeline", "Developed Apache Spark workloads."),
        ]
        resumes = []
        p1 = blueprint.priority_skills.get("P1", ["Terraform"])
        for vid, angle, bullet in variant_angles:
            r = ResumeJSON.model_validate({
                "target_title": blueprint.job.target_title,
                "summary": f"Senior engineer focused on {angle} using {', '.join(p1)}.",
                "technical_skills": {"Core": list(p1)},
                "experience": [
                    {
                        "company": "Company A",
                        "title": "Engineer",
                        "bullets": [bullet, f"Supported {angle} platform reliability at scale."],
                    }
                ],
                "projects": [],
                "certifications": [],
                "variant_id": vid,
                "source_blueprint_hash": blueprint.jd_hash,
            })
            resumes.append(attach_skill_provenance(blueprint, r))

        result = validate_variant_similarity(resumes, threshold=0.98)
        assert result.passed, (
            f"Distinct variants should pass diversity check. Issues: {[i.message for i in result.issues]}"
        )
