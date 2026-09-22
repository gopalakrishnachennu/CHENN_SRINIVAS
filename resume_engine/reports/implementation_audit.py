import importlib
import json
from pathlib import Path

from resume_engine.config.settings import PROJECT_ROOT, REPORT_STORAGE_DIR, ensure_storage_dirs
from resume_engine.models.report_schema import ImplementationAudit, ImplementationModuleStatus


REQUIRED_MODULES = {
    "strategy_builder": "resume_engine.strategy.strategy_builder",
    "variant_planner": "resume_engine.strategy.variant_planner",
    "skill_placement": "resume_engine.strategy.skill_placement",
    "role_positioning": "resume_engine.strategy.role_positioning",
    "prompt_builder": "resume_engine.generation.prompt_builder",
    "openai_generator": "resume_engine.generation.openai_generator",
    "resume_generator": "resume_engine.generation.resume_generator",
    "bullet_enrichment": "resume_engine.generation.bullet_enrichment",
    "blueprint_validator": "resume_engine.validation.blueprint_validator",
    "technology_firewall": "resume_engine.validation.technology_firewall",
    "coverage_validator": "resume_engine.validation.coverage_validator",
    "p4_usage_validator": "resume_engine.validation.p4_usage_validator",
    "ai_tool_placement_validator": "resume_engine.validation.ai_tool_placement_validator",
    "responsibility_validator": "resume_engine.validation.responsibility_validator",
    "hybrid_family_validator": "resume_engine.validation.hybrid_family_validator",
    "laya_validator": "resume_engine.validation.laya_validator",
    "duplicate_validator": "resume_engine.validation.duplicate_validator",
    "role_drift_validator": "resume_engine.validation.role_drift_validator",
    "ats_validator": "resume_engine.validation.ats_validator",
    "variant_similarity_validator": "resume_engine.validation.variant_similarity_validator",
    "variant_regeneration": "resume_engine.validation.variant_regeneration",
    "score_engine": "resume_engine.scoring.score_engine",
    "repair_planner": "resume_engine.repair.repair_planner",
    "targeted_rewriter": "resume_engine.repair.targeted_rewriter",
    "patch_applier": "resume_engine.repair.patch_applier",
    "repair_validator": "resume_engine.repair.repair_validator",
    "outcome_store": "resume_engine.learning.outcome_store",
    "outcome_builder": "resume_engine.learning.outcome_builder",
    "failure_store": "resume_engine.learning.failure_store",
    "strategy_memory": "resume_engine.learning.strategy_memory",
    "eligibility": "resume_engine.learning.eligibility",
    "fingerprint_store": "resume_engine.learning.fingerprint_store",
    "pattern_updater": "resume_engine.learning.pattern_updater",
    "learning_repository": "resume_engine.learning.repository",
    "llm_client": "resume_engine.llm.client",
    "docx_exporter": "resume_engine.export.docx_exporter",
    "pdf_exporter": "resume_engine.export.pdf_exporter",
    "export_service": "resume_engine.export.service",
    "phase3_ui": "resume_engine.ui.app",
    "ui_auth": "resume_engine.ui.auth",
    "phase1_live_harness": "resume_engine.live.phase1_harness",
    "resume_validation_report": "resume_engine.reports.resume_validation_report",
    "behavioral_audit": "resume_engine.reports.behavioral_audit",
    "phase2_pipeline": "resume_engine.pipeline.phase2_pipeline",
}

# Map module -> glob patterns under tests/ that indicate unit coverage.
UNIT_TEST_HINTS = {
    "p4_usage_validator": ["tests/test_wave1_p0.py"],
    "patch_applier": ["tests/test_wave1_p0.py"],
    "variant_planner": ["tests/test_wave2_p1.py"],
    "responsibility_validator": ["tests/test_wave2_p1.py", "tests/test_behavioral_fixtures.py"],
    "laya_validator": ["tests/test_wave2_p1.py"],
    "technology_firewall": ["tests/test_behavioral_fixtures.py", "tests/test_wave2_p1.py"],
    "coverage_validator": ["tests/test_behavioral_fixtures.py", "tests/test_wave1_p0.py"],
    "behavioral_audit": ["tests/test_behavioral_fixtures.py"],
    "phase2_pipeline": ["tests/test_wave1_p0.py", "tests/test_wave2_p1.py"],
    "fingerprint_store": ["tests/test_wave2_p1.py"],
    "variant_regeneration": ["tests/test_wave2_p1.py"],
    "bullet_enrichment": ["tests/test_wave2_p1.py"],
    "strategy_memory": ["tests/test_wave3_learning.py"],
    "eligibility": ["tests/test_wave3_learning.py"],
    "outcome_builder": ["tests/test_wave3_learning.py"],
    "pattern_updater": ["tests/test_wave3_learning.py"],
    "learning_repository": ["tests/test_wave4_infra.py"],
    "llm_client": ["tests/test_wave4_infra.py"],
    "docx_exporter": ["tests/test_phase3_export.py", "tests/test_phase27_gate4.py"],
    "pdf_exporter": ["tests/test_phase3_export.py"],
    "export_service": ["tests/test_phase3_export.py"],
    "phase3_ui": ["tests/test_phase3_export.py", "tests/test_phase27_gate4.py"],
    "ui_auth": ["tests/test_phase27_gate4.py"],
    "phase1_live_harness": ["tests/test_phase27_gate4.py", "tests/test_phase1_offline.py"],
}


def _file_exists(import_path: str) -> bool:
    relative = Path(*import_path.split("."))
    return (PROJECT_ROOT / f"{relative}.py").exists()


def _unit_test_exists(name: str) -> bool:
    hints = UNIT_TEST_HINTS.get(name, [])
    return any((PROJECT_ROOT / hint).exists() for hint in hints)


def _integration_test_exists(name: str) -> bool:
    # Behavioral fixtures act as integration-style offline proofs for core validators.
    if name in {
        "technology_firewall",
        "coverage_validator",
        "ai_tool_placement_validator",
        "hybrid_family_validator",
        "duplicate_validator",
        "ats_validator",
        "variant_similarity_validator",
        "behavioral_audit",
        "responsibility_validator",
    }:
        return (PROJECT_ROOT / "tests/test_behavioral_fixtures.py").exists()
    if name in {"phase2_pipeline", "variant_planner", "fingerprint_store", "variant_regeneration"}:
        return (PROJECT_ROOT / "tests/test_wave2_p1.py").exists() or (
            PROJECT_ROOT / "tests/test_wave1_p0.py"
        ).exists()
    return False


def run_implementation_audit() -> ImplementationAudit:
    modules: dict[str, ImplementationModuleStatus] = {}

    for name, import_path in REQUIRED_MODULES.items():
        exists = _file_exists(import_path)
        imports_ok = False
        import_error = ""
        try:
            importlib.import_module(import_path)
            imports_ok = True
        except Exception as exc:
            import_error = f"{type(exc).__name__}: {exc}"

        unit_exists = _unit_test_exists(name)
        integration_exists = _integration_test_exists(name)

        modules[name] = ImplementationModuleStatus(
            implemented=exists and imports_ok,
            tested=False,  # never set true merely because import succeeded
            details=(
                json.dumps(
                    {
                        "exists": exists,
                        "imports_successfully": imports_ok,
                        "unit_test_exists": unit_exists,
                        "unit_test_passed": None,  # filled by CI/test runner, not assumed
                        "integration_test_exists": integration_exists,
                        "integration_test_passed": None,
                        "live_test_status": "LIVE_TEST_NOT_RUN",
                        "import_error": import_error or None,
                    }
                )
            ),
            exists=exists,
            imports_successfully=imports_ok,
            unit_test_exists=unit_exists,
            unit_test_passed=None,
            integration_test_exists=integration_exists,
            integration_test_passed=None,
            live_test_status="LIVE_TEST_NOT_RUN",
        )

    implemented_count = sum(1 for status in modules.values() if status.implemented)
    total_count = len(modules)
    return ImplementationAudit(
        phase="Phase 2.6",
        modules=modules,
        implemented_count=implemented_count,
        total_count=total_count,
        implementation_percent=round(implemented_count / total_count * 100, 2),
    )


def save_implementation_audit(audit: ImplementationAudit) -> tuple[Path, Path]:
    ensure_storage_dirs()
    json_path = REPORT_STORAGE_DIR / "IMPLEMENTATION_AUDIT.json"
    txt_path = REPORT_STORAGE_DIR / "IMPLEMENTATION_AUDIT.txt"

    serializable = {
        "phase": audit.phase,
        "implemented_count": audit.implemented_count,
        "total_count": audit.total_count,
        "implementation_percent": audit.implementation_percent,
        "modules": {},
    }
    for name, status in audit.modules.items():
        serializable["modules"][name] = {
            "exists": status.exists,
            "imports_successfully": status.imports_successfully,
            "unit_test_exists": status.unit_test_exists,
            "unit_test_passed": status.unit_test_passed,
            "integration_test_exists": status.integration_test_exists,
            "integration_test_passed": status.integration_test_passed,
            "live_test_status": status.live_test_status,
            # legacy fields retained for readers
            "implemented": status.implemented,
            "tested": status.tested,
        }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(serializable, f, indent=2, ensure_ascii=False)

    lines = [
        "PHASE 2.6 IMPLEMENTATION AUDIT",
        "=================================",
        "Note: imports_successfully != tested.",
        "",
    ]
    for module, status in audit.modules.items():
        marker = "[EXISTS]" if status.exists else "[MISSING]"
        lines.append(
            f"{marker} {module} | imports={status.imports_successfully} "
            f"| unit_test_exists={status.unit_test_exists} "
            f"| integration_test_exists={status.integration_test_exists} "
            f"| live={status.live_test_status}"
        )

    lines.extend(
        [
            "",
            "Overall:",
            f"{audit.implemented_count}/{audit.total_count} importable modules",
            f"{audit.implementation_percent:.1f}%",
        ]
    )
    txt_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, txt_path


def main() -> None:
    audit = run_implementation_audit()
    json_path, txt_path = save_implementation_audit(audit)
    print(f"Implementation audit saved: {json_path}")
    print(f"Human-readable audit saved: {txt_path}")
    print(
        f"Importable: {audit.implemented_count}/{audit.total_count} "
        f"({audit.implementation_percent:.1f}%)"
    )


if __name__ == "__main__":
    main()
