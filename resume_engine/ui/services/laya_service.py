"""Laya diagnostics — semantic validation only; never generates prose or invents tech."""

from __future__ import annotations

import os
from typing import Any

from resume_engine.ui.services.audit_service import record_audit_event
from resume_engine.ui.services.config_service import get_effective_setting, set_setting


def laya_status() -> dict[str, Any]:
    available = False
    version = None
    try:
        import laya

        available = True
        version = getattr(laya, "__version__", getattr(laya, "VERSION", "installed"))
    except ImportError:
        available = False

    enabled = True
    try:
        enabled = bool(get_effective_setting("laya_default_enabled"))
    except Exception:  # noqa: BLE001
        enabled = os.getenv("LAYA_ENABLED", "1") not in {"0", "false", "False"}

    return {
        "status": "Available" if available else "Unavailable",
        "available": available,
        "version": version,
        "enabled": enabled,
        "used_for": [
            "JD Family Validation",
            "Hybrid Validation",
            "Responsibility Validation",
            "Semantic Resume Alignment",
            "Seniority semantic validation",
            "Role-drift detection support",
        ],
        "not_used_for": [
            "Resume prose generation",
            "Technology invention",
            "Candidate history changes",
            "Company/timeline changes",
            "Overriding blocked family relationships",
            "Final technology allow-list",
        ],
        "fallback": "Deterministic Python validators remain operational when Laya is OFF",
        "last_validation": None,
        "latency_ms": None,
        "last_result": None,
    }


def set_laya_enabled(enabled: bool, *, actor: str | None = None) -> dict[str, Any]:
    set_setting("laya_default_enabled", enabled, actor=actor, reason="laya_panel_toggle")
    record_audit_event(
        action="laya.toggle",
        actor=actor,
        entity_type="laya",
        new_value={"enabled": enabled},
    )
    return laya_status()
