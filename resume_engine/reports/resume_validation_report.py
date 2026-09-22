import json
from pathlib import Path

from resume_engine.config.settings import REPORT_STORAGE_DIR, ensure_storage_dirs
from resume_engine.models.jd_blueprint import JDBlueprint
from resume_engine.models.validation_schema import ValidationBundle


def save_resume_validation_json(bundle: ValidationBundle) -> Path:
    ensure_storage_dirs()
    path = REPORT_STORAGE_DIR / f"{bundle.resume_id}_validation.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(bundle.model_dump(), f, indent=2, ensure_ascii=False)
    return path


def build_resume_validation_text(blueprint: JDBlueprint, bundle: ValidationBundle) -> str:
    lines = [
        "RESUME VALIDATION REPORT",
        "================================",
        "",
        f"JD: {blueprint.job.target_title}",
        f"Variant: {bundle.variant_id}",
        "",
        "ROLE",
    ]

    for result in bundle.validator_results:
        marker = "[PASS]" if result.passed else "[FAIL]"
        lines.append(f"{marker} {result.name}: {result.score:.1f}")
        for issue in result.issues:
            symbol = "!" if issue.severity == "error" else "-"
            lines.append(f"  {symbol} {issue.code}: {issue.message}")
            if issue.repair_hint:
                lines.append(f"    Repair: {issue.repair_hint}")

    lines.extend(
        [
            "",
            "INTERNAL OPTIMIZATION SCORE / JD_COMPATIBILITY_SCORE",
            f"{bundle.optimization_score:.1f} / 100",
            "",
            f"ACTION: {bundle.action}",
        ]
    )

    if bundle.repair_plan:
        lines.extend(["", "REPAIR PLAN", json.dumps(bundle.repair_plan, indent=2, ensure_ascii=False)])

    return "\n".join(lines)


def save_resume_validation_text(blueprint: JDBlueprint, bundle: ValidationBundle) -> Path:
    ensure_storage_dirs()
    path = REPORT_STORAGE_DIR / f"{bundle.resume_id}_validation.txt"
    path.write_text(build_resume_validation_text(blueprint, bundle), encoding="utf-8")
    return path
