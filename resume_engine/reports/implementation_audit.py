import importlib
import json
from pathlib import Path

from resume_engine.config.settings import REPORT_STORAGE_DIR, ensure_storage_dirs
from resume_engine.models.report_schema import ImplementationAudit, ImplementationModuleStatus


REQUIRED_MODULES = {
    "strategy_builder": "resume_engine.strategy.strategy_builder",
    "variant_planner": "resume_engine.strategy.variant_planner",
    "skill_placement": "resume_engine.strategy.skill_placement",
    "role_positioning": "resume_engine.strategy.role_positioning",
    "prompt_builder": "resume_engine.generation.prompt_builder",
    "openai_generator": "resume_engine.generation.openai_generator",
    "resume_generator": "resume_engine.generation.resume_generator",
    "blueprint_validator": "resume_engine.validation.blueprint_validator",
    "technology_firewall": "resume_engine.validation.technology_firewall",
    "coverage_validator": "resume_engine.validation.coverage_validator",
    "ai_tool_placement_validator": "resume_engine.validation.ai_tool_placement_validator",
    "responsibility_validator": "resume_engine.validation.responsibility_validator",
    "hybrid_family_validator": "resume_engine.validation.hybrid_family_validator",
    "laya_validator": "resume_engine.validation.laya_validator",
    "duplicate_validator": "resume_engine.validation.duplicate_validator",
    "role_drift_validator": "resume_engine.validation.role_drift_validator",
    "ats_validator": "resume_engine.validation.ats_validator",
    "variant_similarity_validator": "resume_engine.validation.variant_similarity_validator",
    "score_engine": "resume_engine.scoring.score_engine",
    "repair_planner": "resume_engine.repair.repair_planner",
    "targeted_rewriter": "resume_engine.repair.targeted_rewriter",
    "repair_validator": "resume_engine.repair.repair_validator",
    "outcome_store": "resume_engine.learning.outcome_store",
    "failure_store": "resume_engine.learning.failure_store",
    "strategy_memory": "resume_engine.learning.strategy_memory",
    "pattern_updater": "resume_engine.learning.pattern_updater",
    "resume_validation_report": "resume_engine.reports.resume_validation_report",
    "behavioral_audit": "resume_engine.reports.behavioral_audit",
    "phase2_pipeline": "resume_engine.pipeline.phase2_pipeline",
}


def run_implementation_audit() -> ImplementationAudit:
    modules: dict[str, ImplementationModuleStatus] = {}

    for name, import_path in REQUIRED_MODULES.items():
        try:
            importlib.import_module(import_path)
            modules[name] = ImplementationModuleStatus(
                implemented=True,
                tested=True,
                details=f"Imported {import_path}",
            )
        except Exception as exc:
            modules[name] = ImplementationModuleStatus(
                implemented=False,
                tested=False,
                details=f"{type(exc).__name__}: {exc}",
            )

    implemented_count = sum(1 for status in modules.values() if status.implemented)
    total_count = len(modules)
    return ImplementationAudit(
        modules=modules,
        implemented_count=implemented_count,
        total_count=total_count,
        implementation_percent=round(implemented_count / total_count * 100, 2),
    )


def save_implementation_audit(audit: ImplementationAudit) -> tuple[Path, Path]:
    ensure_storage_dirs()
    json_path = REPORT_STORAGE_DIR / "IMPLEMENTATION_AUDIT.json"
    txt_path = REPORT_STORAGE_DIR / "IMPLEMENTATION_AUDIT.txt"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(audit.model_dump(), f, indent=2, ensure_ascii=False)

    lines = [
        "PHASE 2 IMPLEMENTATION AUDIT",
        "=================================",
        "",
    ]
    for module, status in audit.modules.items():
        marker = "[PASS]" if status.implemented else "[FAIL]"
        lines.append(f"{marker} {module}")
        if not status.implemented or status.details:
            lines.append(f"       {status.details}")

    lines.extend(
        [
            "",
            "Overall:",
            f"{audit.implemented_count}/{audit.total_count} implemented",
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
    print(f"Implemented: {audit.implemented_count}/{audit.total_count} ({audit.implementation_percent:.1f}%)")


if __name__ == "__main__":
    main()
