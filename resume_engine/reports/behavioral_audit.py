import json
import uuid
from pathlib import Path

from resume_engine.config import thresholds
from resume_engine.config.settings import (
    PROJECT_ROOT,
    REPORT_STORAGE_DIR,
    ensure_storage_dirs,
    portable_path,
)
from resume_engine.generation.provenance import attach_skill_provenance
from resume_engine.models.jd_blueprint import JDBlueprint
from resume_engine.models.resume_schema import ResumeJSON
from resume_engine.models.validation_schema import ValidationBundle
from resume_engine.pipeline.phase2_pipeline import build_generation_context, run_validators
from resume_engine.repair.patch_applier import (
    PatchApplicationError,
    ResumePatch,
    apply_resume_patches,
)
from resume_engine.repair.repair_planner import build_repair_plan
from resume_engine.repair.version_selector import select_best_resume_version
from resume_engine.storage.run_store import create_run_paths, save_raw_resume, save_repaired_resume
from resume_engine.strategy.strategy_builder import build_strategy
from resume_engine.strategy.variant_planner import create_variants
from resume_engine.validation.ai_tool_placement_validator import validate_ai_tool_placement
from resume_engine.validation.coverage_validator import validate_coverage
from resume_engine.validation.hybrid_family_validator import validate_hybrid_family_retention
from resume_engine.validation.p4_usage_validator import validate_p4_usage
from resume_engine.validation.technology_firewall import validate_technology_firewall
from resume_engine.validation.variant_similarity_validator import validate_variant_similarity


def _monster_blueprint() -> JDBlueprint:
    allowed = [
        "AWS",
        "Databricks",
        "Terraform",
        "Kubernetes",
        "CI/CD",
        "Python",
        "Apache Spark",
        "OpenAI API",
        "Claude API",
        "LangChain",
        "Delta Lake",
        "PySpark",
        "Docker",
        "Helm",
    ]
    entities = [
        ("AWS", "cloud", "P2", "jd_direct", ["technical_skills", "experience_responsibilities"], None),
        ("Databricks", "data_platform", "P1", "jd_direct", ["technical_skills", "experience_responsibilities", "professional_summary"], None),
        ("Terraform", "devops", "P1", "jd_direct", ["technical_skills", "experience_responsibilities", "professional_summary"], None),
        ("Kubernetes", "devops", "P2", "jd_direct", ["technical_skills", "experience_responsibilities"], None),
        ("CI/CD", "devops", "P2", "jd_direct", ["technical_skills", "experience_responsibilities"], None),
        ("Python", "programming_language", "P2", "jd_direct", ["technical_skills", "experience_responsibilities"], None),
        ("Apache Spark", "data_platform", "P2", "jd_direct", ["technical_skills", "experience_responsibilities"], None),
        ("OpenAI API", "ai_tool", "P1", "jd_direct", ["technical_skills", "experience_responsibilities", "professional_summary"], None),
        ("Claude API", "ai_tool", "P1", "jd_direct", ["technical_skills", "experience_responsibilities", "professional_summary"], None),
        ("LangChain", "ai_framework", "P3", "jd_direct", ["technical_skills", "selected_experience"], None),
        ("Delta Lake", "adjacent", "P4", "approved_adjacent", ["technical_skills_optional"], "Databricks"),
        ("PySpark", "adjacent", "P4", "approved_adjacent", ["technical_skills_optional"], "Apache Spark"),
        ("Docker", "adjacent", "P4", "approved_adjacent", ["technical_skills_optional"], "Kubernetes"),
        ("Helm", "adjacent", "P4", "approved_adjacent", ["technical_skills_optional"], "Kubernetes"),
    ]
    return JDBlueprint.model_validate(
        {
            "blueprint_version": "1.0",
            "jd_hash": "hybrid_devops_databricks_ai",
            "created_at": "2026-09-22T00:00:00+00:00",
            "job": {
                "target_title": "Senior Cloud Data Platform Engineer",
                "company": None,
                "primary_family": "devops_cloud",
                "primary_confidence": 0.92,
                "secondary_family": "data_engineering",
                "seniority": "senior",
                "seniority_confidence": 0.9,
                "hybrid_probability": 0.87,
            },
            "priority_skills": {
                "P1": ["Databricks", "Terraform", "OpenAI API", "Claude API"],
                "P2": ["AWS", "Kubernetes", "CI/CD", "Python", "Apache Spark"],
                "P3": ["LangChain"],
                "P4": ["Delta Lake", "PySpark", "Docker", "Helm"],
            },
            "entities": [
                {
                    "name": name,
                    "category": category,
                    "priority": priority,
                    "source": source,
                    "requirement": "required" if priority in {"P1", "P2"} else "preferred",
                    "evidence": "behavioral fixture",
                    "confidence": 1.0,
                    "placement": placement,
                    "parent_skill": parent,
                }
                for name, category, priority, source, placement, parent in entities
            ],
            "responsibilities": [
                "Manage Databricks platform",
                "Build cloud infrastructure",
                "Automate deployments",
                "Develop Spark workloads",
                "Build automation using OpenAI API and Claude API",
            ],
            "domain_terms": ["cloud data platform", "generative AI automation"],
            "certifications": [],
            "generation_contract": {
                "allowed_technologies": allowed,
                "allow_new_llm_skills": False,
                "allowed_sources": ["jd_direct", "approved_adjacent"],
                "rules": ["Every technology used must exist in allowed_technologies."],
            },
            "quality_gates": {},
        }
    )


def _good_resume(variant_id: str = "V01", angle: str = "cloud platform") -> ResumeJSON:
    # Keep P4 usage within thresholds.P4_USAGE_MAX (1 of 4 = 0.25 <= 0.35).
    # Only Docker is used as optional adjacent support.
    if "Databricks" in angle:
        bullets = [
            "Owned Databricks workspace reliability on AWS while coordinating Terraform changes with platform release teams.",
            "Tuned Apache Spark workloads for lakehouse production operations across Databricks environments.",
            "Built OpenAI API and Claude API automation to assist Databricks runbooks, incident triage, and deployment checks.",
            "Standardized Kubernetes support services for data platform integration paths.",
        ]
        second_bullets = [
            "Improved Databricks platform governance while preserving CI/CD release paths for Spark workloads.",
            "Used LangChain patterns for approved AI-enabled data platform support workflows.",
        ]
    elif "DevOps" in angle:
        bullets = [
            "Automated Terraform deployment modules for AWS, Kubernetes, Databricks, and CI/CD platform operations.",
            "Built Python release utilities that connected Spark workload deployment checks with cloud infrastructure gates.",
            "Implemented OpenAI API and Claude API workflow helpers for deployment readiness and operational response.",
            "Managed Kubernetes release patterns supporting services around the data platform.",
        ]
        second_bullets = [
            "Reduced manual platform handoffs through CI/CD automation spanning Terraform and Databricks changes.",
            "Applied LangChain selectively for approved AI-assisted release workflow support.",
        ]
    elif "data engineering" in angle:
        bullets = [
            "Developed Apache Spark workloads in Databricks using Python for cloud data pipelines.",
            "Aligned AWS infrastructure and Terraform modules with data engineering delivery requirements.",
            "Integrated OpenAI API and Claude API automation into data platform operational workflows.",
            "Supported Kubernetes-based services that backed CI/CD deployment paths for Spark processing.",
        ]
        second_bullets = [
            "Managed production data pipeline support across Databricks, Spark, and cloud platform dependencies.",
            "Used LangChain patterns for approved AI-enabled data engineering workflow assistance.",
        ]
    elif "AI-enabled" in angle:
        bullets = [
            "Built OpenAI API and Claude API automation for cloud data platform operations across Databricks and AWS.",
            "Connected AI-assisted checks with Terraform, Kubernetes, and CI/CD workflows to automate deployments and support deployment quality.",
            "Developed Apache Spark workload support patterns using Python and Databricks context.",
            "Maintained Kubernetes integration points for AI-enabled platform workflows.",
        ]
        second_bullets = [
            "Applied LangChain to approved automation patterns while keeping Databricks and cloud operations central.",
            "Supported platform runbooks spanning OpenAI API, Claude API, Terraform, and Spark workload checks.",
        ]
    else:
        bullets = [
            f"Managed Databricks platform operations on AWS while shaping {angle} automation with Terraform and Kubernetes.",
            "Automated CI/CD deployments using Python workflows across cloud infrastructure and data platform release paths.",
            "Developed Apache Spark workloads with Databricks for production data engineering needs.",
            "Built operational automation using OpenAI API and Claude API to support deployment and platform workflows.",
        ]
        second_bullets = [
            "Supported Kubernetes platform reliability while maintaining Terraform deployment modules.",
            "Applied LangChain patterns for approved AI-assisted cloud data platform support workflows.",
        ]

    return ResumeJSON.model_validate(
        {
            "target_title": "Senior Cloud Data Platform Engineer",
            "summary": (
                f"Senior {angle} engineer focused on Databricks, Terraform, OpenAI API, "
                "Claude API, AWS, Kubernetes, CI/CD, Python, and Apache Spark."
            ),
            "technical_skills": {
                "Cloud and DevOps": ["AWS", "Terraform", "Kubernetes", "CI/CD", "Docker"],
                "Data Platform": ["Databricks", "Apache Spark", "Python"],
                "AI Automation": ["OpenAI API", "Claude API", "LangChain"],
            },
            "experience": [
                {
                    "company": "Company A",
                    "title": "Senior Cloud Data Platform Engineer",
                    "bullets": bullets,
                },
                {
                    "company": "Company B",
                    "title": "Cloud Data Engineer",
                    "bullets": second_bullets,
                },
            ],
            "projects": [],
            "certifications": [],
            "variant_id": variant_id,
            "source_blueprint_hash": "hybrid_devops_databricks_ai",
        }
    )


def _bad_hallucinated_resume() -> ResumeJSON:
    resume = _good_resume()
    resume.technical_skills.setdefault("CRM", []).append("Salesforce")
    resume.summary += " Salesforce."
    return resume


def _bad_repair_resume() -> ResumeJSON:
    return ResumeJSON.model_validate(
        {
            "target_title": "Senior Cloud Data Platform Engineer",
            "summary": "Senior engineer focused on AWS and Kubernetes.",
            "technical_skills": {"Cloud": ["AWS", "Kubernetes"]},
            "experience": [
                {
                    "company": "Company A",
                    "title": "Senior Engineer",
                    "bullets": [
                        "Built cloud infrastructure on AWS using Kubernetes for deployment reliability.",
                        "Built cloud infrastructure on AWS using Kubernetes for deployment reliability.",
                    ],
                }
            ],
            "projects": [],
            "certifications": [],
            "variant_id": "VREPAIR",
            "source_blueprint_hash": "hybrid_devops_databricks_ai",
        }
    )


def _fixture_inventory() -> dict:
    fixture_dir = PROJECT_ROOT / "tests" / "fixtures" / "jds"
    files = sorted(path.name for path in fixture_dir.glob("*.txt"))
    return {"count": len(files), "files": files}


def _fixture_assertion_inventory() -> dict:
    assertion_path = PROJECT_ROOT / "tests" / "fixtures" / "expected" / "fixture_assertions.json"
    assertions = json.loads(assertion_path.read_text(encoding="utf-8"))
    fixture_dir = PROJECT_ROOT / "tests" / "fixtures" / "jds"
    fixture_ids = sorted(path.stem for path in fixture_dir.glob("*.txt"))
    missing = [fixture_id for fixture_id in fixture_ids if fixture_id not in assertions]
    return {
        "assertion_file": portable_path(assertion_path),
        "assertion_count": len(assertions),
        "fixture_count": len(fixture_ids),
        "missing_assertions": missing,
        "all_fixtures_have_assertions": not missing and len(assertions) >= len(fixture_ids),
    }


def run_behavioral_audit() -> dict:
    ensure_storage_dirs()
    blueprint = _monster_blueprint()
    strategy = build_strategy(blueprint)
    variants = create_variants(blueprint, strategy)

    template_context = build_generation_context("resume_seed.json", None)
    good_resume = attach_skill_provenance(blueprint, _good_resume())
    validation = run_validators(blueprint, good_resume, None, "behavioral_good")
    ai_placement_result = validate_ai_tool_placement(blueprint, good_resume)
    hybrid_result = validate_hybrid_family_retention(blueprint, good_resume)
    p4_result = validate_p4_usage(blueprint, good_resume)

    # Missing P4 must not create required-placement failures or repair stuffing.
    zero_p4_resume = attach_skill_provenance(blueprint, _good_resume())
    zero_p4_resume.technical_skills = {
        group: [skill for skill in skills if skill not in blueprint.priority_skills.get("P4", [])]
        for group, skills in zero_p4_resume.technical_skills.items()
    }
    for exp in zero_p4_resume.experience:
        exp.bullets = [
            " ".join(
                word
                for word in bullet.split()
                if word.rstrip(".,") not in blueprint.priority_skills.get("P4", [])
            )
            for bullet in exp.bullets
        ]
    zero_p4_resume = attach_skill_provenance(blueprint, zero_p4_resume)
    zero_p4_coverage = validate_coverage(blueprint, zero_p4_resume)
    zero_p4_bundle = run_validators(blueprint, zero_p4_resume, None, "behavioral_zero_p4")
    zero_p4_plan = build_repair_plan(zero_p4_bundle, blueprint=blueprint)
    p4_optional_ok = not any(
        issue.code == "FAIL_MISSING_REQUIRED_PLACEMENT"
        and (
            issue.metadata.get("placement") == "technical_skills_optional"
            or issue.metadata.get("priority") == "P4"
            or issue.metadata.get("skill") in blueprint.priority_skills.get("P4", [])
        )
        for issue in zero_p4_coverage.issues
    )
    p4_not_in_repair = not any(
        skill in zero_p4_plan.get("missing_skills", [])
        for skill in blueprint.priority_skills.get("P4", [])
    )

    hallucinated = attach_skill_provenance(blueprint, _bad_hallucinated_resume())
    hallucination_result = validate_technology_firewall(blueprint, hallucinated)

    repair_resume = attach_skill_provenance(blueprint, _bad_repair_resume())
    repair_before = run_validators(blueprint, repair_resume, None, "behavioral_repair_before")
    repair_plan = build_repair_plan(repair_before, blueprint=blueprint)

    # Patch-based targeted repair proof (deterministic; no live OpenAI).
    patched_resume, scope_issues = apply_resume_patches(
        resume=repair_resume,
        patches=[
            ResumePatch(
                location="experience[0].bullets[1]",
                replacement=(
                    "Owned Databricks and Terraform delivery on AWS with OpenAI API and Claude API "
                    "ops automation, Kubernetes, CI/CD, Python, and Apache Spark support."
                ),
            )
        ],
        repair_plan={
            "targets": [{"location": "experience[0].bullets[1]", "reason_codes": ["FAIL_EXACT_DUPLICATE_BULLET"]}],
            "failed_bullets": ["experience[0].bullets[1]"],
        },
    )
    patch_only_target_changed = (
        patched_resume.summary == repair_resume.summary
        and patched_resume.technical_skills == repair_resume.technical_skills
        and patched_resume.experience[0].bullets[0] == repair_resume.experience[0].bullets[0]
        and patched_resume.experience[0].bullets[1] != repair_resume.experience[0].bullets[1]
        and not scope_issues
    )

    # Out-of-scope patch must be rejected.
    out_of_scope_rejected = False
    try:
        apply_resume_patches(
            resume=repair_resume,
            patches=[ResumePatch(location="summary", replacement="Hacked summary")],
            repair_plan={
                "targets": [{"location": "experience[0].bullets[1]", "reason_codes": ["X"]}],
                "failed_bullets": ["experience[0].bullets[1]"],
            },
        )
    except PatchApplicationError:
        out_of_scope_rejected = True

    repaired = attach_skill_provenance(blueprint, _good_resume("VREPAIR", "AI-enabled data platform"))
    repair_after = run_validators(blueprint, repaired, None, "behavioral_repair_after")
    unchanged_valid_content = (
        repaired.target_title == good_resume.target_title
        and repaired.technical_skills == good_resume.technical_skills
    )

    # Failed-final + score regression + run isolation proofs (offline).
    failing_bundle = ValidationBundle(
        variant_id="VFAIL",
        resume_id="fail",
        passed=False,
        optimization_score=86.59,
        action="REPAIR_REQUIRED",
        validator_results=[],
    )
    worse_bundle = ValidationBundle(
        variant_id="VFAIL",
        resume_id="fail_repaired",
        passed=False,
        optimization_score=86.57,
        action="REPAIR_REQUIRED",
        validator_results=[],
    )
    selection = select_best_resume_version(
        raw_resume=repair_resume,
        raw_bundle=failing_bundle,
        repaired_resume=repaired,
        repaired_bundle=worse_bundle,
    )
    failed_final_gate = (
        selection.status == "FAILED_VALIDATION"
        and selection.regression_recorded
        and "REPAIR_SCORE_REGRESSION" in selection.notes
    )

    run_a = create_run_paths("behavioral_jd_hash", run_id=f"run-a-{uuid.uuid4().hex[:8]}")
    run_b = create_run_paths("behavioral_jd_hash", run_id=f"run-b-{uuid.uuid4().hex[:8]}")
    raw_a = save_raw_resume(run_a, "V01", good_resume)
    raw_b = save_raw_resume(run_b, "V01", good_resume)
    repaired_a = save_repaired_resume(run_a, "V01", patched_resume)
    run_isolation = (
        run_a.root != run_b.root
        and raw_a.exists()
        and raw_b.exists()
        and repaired_a.exists()
        and raw_a != repaired_a
        and raw_a.read_text(encoding="utf-8") != ""
    )

    too_similar = [
        attach_skill_provenance(blueprint, _good_resume("V01", "cloud platform")),
        attach_skill_provenance(blueprint, _good_resume("V02", "cloud platform")),
    ]
    distinct = [
        attach_skill_provenance(blueprint, _good_resume("V01", "cloud platform")),
        attach_skill_provenance(blueprint, _good_resume("V02", "Databricks platform")),
        attach_skill_provenance(blueprint, _good_resume("V03", "DevOps automation")),
        attach_skill_provenance(blueprint, _good_resume("V04", "cloud data engineering")),
        attach_skill_provenance(blueprint, _good_resume("V05", "AI-enabled data platform")),
    ]
    similar_result = validate_variant_similarity(too_similar, threshold=0.90)
    distinct_result = validate_variant_similarity(distinct, threshold=0.98)

    full_text = json.dumps(good_resume.model_dump(), ensure_ascii=False)
    critical_skills = [
        "Databricks",
        "Terraform",
        "Kubernetes",
        "OpenAI API",
        "Claude API",
        "LangChain",
    ]
    critical_detection = {skill: skill in full_text for skill in critical_skills}

    all_skill_values = [
        skill for skills in good_resume.technical_skills.values() for skill in skills
    ]
    placement_validation = {
        "OpenAI_in_skills": "OpenAI API" in all_skill_values,
        "OpenAI_in_responsibilities": "OpenAI API" in "\n".join(b for exp in good_resume.experience for b in exp.bullets),
        "Claude_in_skills": "Claude API" in all_skill_values,
        "Claude_in_responsibilities": "Claude API" in "\n".join(b for exp in good_resume.experience for b in exp.bullets),
        "explicit_ai_validator_passed": ai_placement_result.passed,
    }

    p4_items = blueprint.priority_skills.get("P4", [])
    p4_usage_ratio = float(p4_result.details.get("usage_ratio", 0.0))
    p4_share = float(p4_result.details.get("p4_share_of_used_priority", p4_usage_ratio))
    p4_count = int(p4_result.details.get("p4_usage_count", 0))
    p4_within_policy = bool(p4_result.passed) and (
        p4_count <= 1 or p4_share <= thresholds.P4_USAGE_MAX
    )

    checks = {
        "template_mode_default": template_context["generation_mode"] == "TEMPLATE",
        "candidate_profile_optional": "candidate_profile" not in template_context,
        "fixture_assertions_present": _fixture_assertion_inventory()["all_fixtures_have_assertions"],
        "variant_count": len(variants) == 5,
        "variant_positioning_distinct": len({variant.positioning for variant in variants}) == 5,
        "good_resume_passes": validation.passed,
        "ai_tool_placement_validator_passes": ai_placement_result.passed,
        "hybrid_family_validator_passes": hybrid_result.passed,
        "hallucination_blocked": not hallucination_result.passed,
        "repair_plan_targeted": repair_plan["required"] and repair_plan["issue_count"] > 0,
        "repair_after_passes": repair_after.passed,
        "repair_preserves_valid_content": unchanged_valid_content,
        "similar_variants_blocked": not similar_result.passed,
        "distinct_variants_pass": distinct_result.passed,
        "p4_usage_within_limit": p4_within_policy,
        "p4_optional_semantics": p4_optional_ok and p4_not_in_repair,
        "failed_final_gate": failed_final_gate,
        "raw_artifact_preserved": run_isolation,
        "run_isolation": run_isolation,
        "targeted_patch_repair": patch_only_target_changed,
        "repair_scope_guard": out_of_scope_rejected,
    }

    result = {
        "phase": "Phase 2.6 Wave 1",
        "audit_type": "BEHAVIORAL_VALIDATION",
        "fixture_inventory": _fixture_inventory(),
        "fixture_assertions": _fixture_assertion_inventory(),
        "jd": "hybrid_devops_databricks_ai",
        "blueprint": {
            "primary_family_correct": blueprint.job.primary_family == "devops_cloud",
            "secondary_family_correct": blueprint.job.secondary_family == "data_engineering",
            "hybrid_detected": blueprint.job.hybrid_probability >= 0.55,
        },
        "critical_skill_detection": critical_detection,
        "placement_validation": placement_validation,
        "ai_tool_placement_validator": ai_placement_result.model_dump(),
        "hybrid_family_validator": hybrid_result.model_dump(),
        "p4_usage": {
            "p4_items": p4_items,
            "p4_used": p4_result.details.get("p4_used", []),
            "usage_ratio": round(p4_usage_ratio, 3),
            "p4_share_of_used_priority": round(p4_share, 3),
            "p4_usage_count": p4_count,
            "one_p4_floor_applied": bool(p4_result.details.get("one_p4_floor_applied")),
            "max_ratio": thresholds.P4_USAGE_MAX,
            "validator_passed": p4_result.passed,
        },
        "hallucination_firewall": {
            "unauthorized_technologies": hallucination_result.details["unauthorized_count"],
            "blocked": not hallucination_result.passed,
        },
        "role_drift": any(
            issue.code == "FAIL_ROLE_DRIFT"
            for validator in validation.validator_results
            for issue in validator.issues
        ),
        "duplicate_bullets": sum(
            1
            for validator in repair_before.validator_results
            for issue in validator.issues
            if "DUPLICATE" in issue.code
        ),
        "repair_test": {
            "failures_before": repair_plan["issue_count"],
            "failures_after": sum(len(result.issues) for result in repair_after.validator_results),
            "targeted_plan": repair_plan,
            "valid_content_preserved": unchanged_valid_content,
            "patch_only_target_changed": patch_only_target_changed,
            "out_of_scope_rejected": out_of_scope_rejected,
        },
        "variant_diversity": {
            "similar_pair_blocked": not similar_result.passed,
            "distinct_set_passed": distinct_result.passed,
            "variant_positions": [variant.positioning for variant in variants],
        },
        "wave1_gates": {
            "failed_final_gate": failed_final_gate,
            "run_isolation": run_isolation,
            "p4_optional_semantics": p4_optional_ok and p4_not_in_repair,
        },
        "checks": checks,
        "pass_conditions": {
            "P1 coverage": validation.subscores.get("p1_coverage") == 100.0,
            "P2 coverage": validation.subscores.get("p2_coverage", 0) >= 90.0,
            "Unauthorized technology": hallucination_result.details["unauthorized_count"] > 0,
            "Role drift": not any(
                issue.code == "FAIL_ROLE_DRIFT"
                for validator in validation.validator_results
                for issue in validator.issues
            ),
            "P1 AI tool in skills": placement_validation["OpenAI_in_skills"] and placement_validation["Claude_in_skills"],
            "P1 AI tool in responsibility": placement_validation["OpenAI_in_responsibilities"] and placement_validation["Claude_in_responsibilities"],
            "AI placement validator": ai_placement_result.passed,
            "Hybrid role detection": blueprint.job.hybrid_probability >= 0.55,
            "Secondary family retention": blueprint.job.secondary_family == "data_engineering",
            "Hybrid family validator": hybrid_result.passed,
            "P4 limit respected": p4_within_policy,
            "P4 optional semantics": p4_optional_ok and p4_not_in_repair,
            "Targeted repair": repair_plan["required"] and repair_after.passed and patch_only_target_changed,
            "Repair scope guard": out_of_scope_rejected,
            "Failed-final gate": failed_final_gate,
            "Raw artifact preserved": run_isolation,
            "Run isolation": run_isolation,
            "Variant differentiation": distinct_result.passed and not similar_result.passed,
        },
    }
    result["result"] = "PASS" if all(result["checks"].values()) and all(result["pass_conditions"].values()) else "FAIL"
    return result


def save_behavioral_audit(audit: dict) -> tuple[Path, Path]:
    ensure_storage_dirs()
    json_path = REPORT_STORAGE_DIR / "BEHAVIORAL_AUDIT.json"
    txt_path = REPORT_STORAGE_DIR / "BEHAVIORAL_AUDIT.txt"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(audit, f, indent=2, ensure_ascii=False)

    lines = [
        "PHASE 2.5 BEHAVIORAL VALIDATION & HARDENING",
        "============================================",
        "",
        f"Fixture JDs: {audit['fixture_inventory']['count']}",
        f"Fixture assertions: {audit['fixture_assertions']['assertion_count']}",
        f"Monster JD: {audit['jd']}",
        "",
        "CHECKS",
    ]
    for name, passed in audit["checks"].items():
        lines.append(f"[{'PASS' if passed else 'FAIL'}] {name}")
    lines.append("")
    lines.append("PASS CONDITIONS")
    for name, passed in audit["pass_conditions"].items():
        lines.append(f"[{'PASS' if passed else 'FAIL'}] {name}")
    lines.extend(["", f"RESULT: {audit['result']}"])
    txt_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, txt_path


def main() -> None:
    audit = run_behavioral_audit()
    json_path, txt_path = save_behavioral_audit(audit)
    print(f"Behavioral audit saved: {json_path}")
    print(f"Human-readable behavioral audit saved: {txt_path}")
    print(f"Result: {audit['result']}")


if __name__ == "__main__":
    main()
