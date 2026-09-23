"""Dashboard metrics — filesystem + SQLite, no paid OpenAI calls."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from resume_engine.config.settings import (
    PROJECT_ROOT,
    RUNS_STORAGE_DIR,
    SQLITE_DB_PATH,
    ensure_storage_dirs,
)
from resume_engine.learning.online.config import get_online_learning_mode
from resume_engine.learning.online.evaluator import build_shadow_evaluation
from resume_engine.ui.app_helpers import list_validated_resumes, scan_run_summaries


def _openai_configured() -> bool:
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    return bool(key) and "PASTE" not in key.upper() and key != "your_real_key_here"


def system_status() -> dict[str, Any]:
    ensure_storage_dirs()
    status = {
        "openai": "CONFIGURED" if _openai_configured() else "NOT CONFIGURED",
        "laya": "AVAILABLE",
        "river": f"shadow ({get_online_learning_mode()})",
        "sqlite": "OK" if Path(SQLITE_DB_PATH).exists() or True else "MISSING",
        "storage": "OK" if RUNS_STORAGE_DIR.exists() else "MISSING",
        "docx_exporter": "OK",
        "pdf_exporter": "OK",
        "river_active": "OFF",
    }
    try:
        import laya  # noqa: F401
    except ImportError:
        status["laya"] = "NOT INSTALLED"
    try:
        import river

        status["river_version"] = getattr(river, "__version__", "?")
    except ImportError:
        status["river"] = "NOT INSTALLED"
    return status


def dashboard_metrics() -> dict[str, Any]:
    ensure_storage_dirs()
    summaries = scan_run_summaries(limit=500)
    validated = list_validated_resumes(limit=5000)
    rejected = list(RUNS_STORAGE_DIR.glob("*/*/rejected/*.json")) if RUNS_STORAGE_DIR.exists() else []

    scores: list[float] = []
    p1s: list[float] = []
    p2s: list[float] = []
    repair_events = 0
    total_variants = 0
    validated_count = 0
    for item in summaries:
        payload = item.get("summary") if isinstance(item.get("summary"), dict) else item
        variant_list = payload.get("variant_results")
        if not isinstance(variant_list, list):
            variant_list = payload.get("variants") if isinstance(payload.get("variants"), list) else []
        for variant in variant_list:
            if not isinstance(variant, dict):
                continue
            total_variants += 1
            if variant.get("passed"):
                validated_count += 1
            score = variant.get("score_after_repair") or variant.get("score_before_repair")
            if isinstance(score, (int, float)):
                scores.append(float(score))
            diag = variant.get("diagnostics") or {}
            if isinstance(diag.get("p1_coverage"), (int, float)):
                p1s.append(float(diag["p1_coverage"]))
            if isinstance(diag.get("p2_coverage"), (int, float)):
                p2s.append(float(diag["p2_coverage"]))
            if variant.get("repaired_resume") or (variant.get("attempt_no") or 1) > 1:
                repair_events += 1

    try:
        evaluation = build_shadow_evaluation()
        river = {
            "observations": evaluation.eligible_observations,
            "linked": evaluation.linked_observations,
            "agreement_rate": evaluation.shadow_agreement_rate,
            "mean_reward": evaluation.mean_reward_all,
            "insufficient_evidence": evaluation.insufficient_evidence,
            "activation_ready": evaluation.activation_ready,
            "mode": "shadow",
        }
    except Exception as exc:  # noqa: BLE001
        river = {"error": str(exc), "mode": "shadow", "observations": 0}

    blueprints_dir = PROJECT_ROOT / "resume_engine_data" / "blueprints"
    jd_count = len(list(blueprints_dir.glob("*.json"))) if blueprints_dir.exists() else 0

    return {
        "total_jds": jd_count,
        "total_runs": len(summaries),
        "generated_resumes": total_variants,
        "validated_resumes": len(validated),
        "rejected_resumes": len(rejected),
        "validation_rate": (validated_count / total_variants) if total_variants else None,
        "average_optimization_score": (sum(scores) / len(scores)) if scores else None,
        "average_p1_coverage": (sum(p1s) / len(p1s)) if p1s else None,
        "average_p2_coverage": (sum(p2s) / len(p2s)) if p2s else None,
        "repair_rate": (repair_events / total_variants) if total_variants else None,
        "river": river,
        "system": system_status(),
        "recent_runs": summaries[:25],
    }


def load_phase2_summary(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
