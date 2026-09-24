"""System / health page — no paid OpenAI calls."""

from __future__ import annotations

import os
import platform
import subprocess
from typing import Any

from resume_engine.config.settings import PROJECT_ROOT, STORAGE_DIR, get_sqlite_db_path
from resume_engine.learning.online import config as online_config
from resume_engine.learning.online.policy_store import load_metadata, policy_dir
from resume_engine.ui.services.dashboard_service import system_status_lite as system_status


def git_commit() -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(PROJECT_ROOT),
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except Exception:  # noqa: BLE001
        return None


def workflow_health() -> dict[str, Any]:
    """Integrity snapshot for Advanced → System."""
    from resume_engine.maintenance.reconcile import check_integrity

    report = check_integrity()
    return {
        "jobs_total": report["jobs_total"],
        "jobs_ready": report["jobs_ready"],
        "jobs_needs_analysis": report["jobs_needs_analysis"],
        "jobs_failed": report["jobs_failed"],
        "missing_blueprints": sum(
            1 for i in report["issues"] if i["code"] == "READY_MISSING_BLUEPRINT"
        ),
        "stale_blueprints": sum(
            1 for i in report["issues"] if i["code"] == "STALE_BLUEPRINT_HASH"
        ),
        "candidates": report["candidates"],
        "candidates_without_primary": report["candidates_without_primary"],
        "stale_matches": report["stale_matches"],
        "issue_count": report["issue_count"],
        "ok": report["ok"],
        "river_mode": "SHADOW",
    }


def system_info() -> dict[str, Any]:
    import river

    meta = {}
    try:
        meta = load_metadata() or {}
    except Exception:  # noqa: BLE001
        meta = {}

    versions = {
        "python": platform.python_version(),
        "river": getattr(river, "__version__", None),
        "openai": None,
        "laya": None,
        "flask": None,
    }
    try:
        import openai

        versions["openai"] = getattr(openai, "__version__", None)
    except ImportError:
        versions["openai"] = None
    try:
        import laya

        versions["laya"] = getattr(laya, "__version__", getattr(laya, "VERSION", "installed"))
    except ImportError:
        versions["laya"] = None
    try:
        from importlib.metadata import version as pkg_version

        versions["flask"] = pkg_version("flask")
    except Exception:  # noqa: BLE001
        versions["flask"] = None

    policy_path = policy_dir() / "policy.pkl"
    integrity = workflow_health()
    return {
        "app_version": "phase-3.2",
        "git_commit": git_commit(),
        "versions": versions,
        "sqlite_location": str(get_sqlite_db_path()),
        "storage_location": str(STORAGE_DIR),
        "policy_version": online_config.ONLINE_POLICY_VERSION,
        "feature_schema_version": meta.get("feature_schema_version"),
        "reward_schema_version": online_config.ONLINE_REWARD_SCHEMA_VERSION,
        "policy_file_exists": policy_path.exists(),
        "openai_key_status": "CONFIGURED" if (os.getenv("OPENAI_API_KEY") or "").strip() and "PASTE" not in (os.getenv("OPENAI_API_KEY") or "").upper() else "NOT CONFIGURED",
        "health": system_status(),
        "integrity": integrity,
        "river_active": "OFF",
    }
