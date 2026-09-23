"""River shadow learning UI service — active mode locked."""

from __future__ import annotations

from typing import Any

from resume_engine.learning.online.config import (
    ONLINE_MIN_ACTION_OBSERVATIONS,
    ONLINE_MIN_TOTAL_OBSERVATIONS,
    ONLINE_POLICY_VERSION,
    ONLINE_REWARD_SCHEMA_VERSION,
    get_online_learning_mode,
)
from resume_engine.learning.online.evaluator import build_shadow_evaluation, write_evaluation_report
from resume_engine.learning.online.policy_store import load_metadata
from resume_engine.learning.online.replay import replay_from_repository
from resume_engine.learning.repository import get_default_repository
from resume_engine.ui.services.audit_service import record_audit_event

ACTIVE_MODE_LOCKED_MESSAGE = (
    "Production activation locked. Requires future Phase 2.8 Gate 2 approval."
)


def learning_dashboard() -> dict[str, Any]:
    evaluation = build_shadow_evaluation()
    meta = {}
    try:
        meta = load_metadata() or {}
    except Exception:  # noqa: BLE001
        meta = {}
    import river

    return {
        "mode": get_online_learning_mode(),
        "production_control": "OFF",
        "active_mode_locked": True,
        "active_mode_message": ACTIVE_MODE_LOCKED_MESSAGE,
        "policy_version": evaluation.policy_version or ONLINE_POLICY_VERSION,
        "river_version": getattr(river, "__version__", None),
        "feature_schema_version": meta.get("feature_schema_version"),
        "reward_schema_version": ONLINE_REWARD_SCHEMA_VERSION,
        "evaluation": evaluation.model_dump() if hasattr(evaluation, "model_dump") else dict(evaluation),
        "required_observations": ONLINE_MIN_TOTAL_OBSERVATIONS,
        "required_per_action": ONLINE_MIN_ACTION_OBSERVATIONS,
        "metadata": meta,
    }


def refresh_evaluation(*, actor: str | None = None) -> dict[str, Any]:
    data = learning_dashboard()
    record_audit_event(action="learning.refresh", actor=actor, entity_type="online_learning")
    return data


def write_report(*, actor: str | None = None) -> str:
    evaluation = build_shadow_evaluation()
    path = write_evaluation_report(evaluation)
    record_audit_event(
        action="learning.write_report",
        actor=actor,
        entity_type="online_learning",
        metadata={"path": str(path)},
    )
    return str(path)


def replay_dry(*, actor: str | None = None) -> dict[str, Any]:
    report = replay_from_repository(dry_run=True)
    record_audit_event(action="learning.replay_dry", actor=actor, entity_type="online_learning")
    return report.model_dump() if hasattr(report, "model_dump") else dict(report)


def replay_train(*, actor: str | None = None, confirmed: bool = False) -> dict[str, Any]:
    if not confirmed:
        raise PermissionError("Historical replay train requires confirmation")
    report = replay_from_repository(dry_run=False)
    record_audit_event(action="learning.replay_train", actor=actor, entity_type="online_learning")
    return report.model_dump() if hasattr(report, "model_dump") else dict(report)


def try_enable_active_mode() -> None:
    raise PermissionError(ACTIVE_MODE_LOCKED_MESSAGE)


def list_observations(limit: int = 200) -> list[dict[str, Any]]:
    return get_default_repository().list_online_observations(limit=limit)


def list_decisions(limit: int = 200) -> list[dict[str, Any]]:
    return get_default_repository().list_online_decisions(limit=limit)


def get_decision(decision_id: int) -> dict[str, Any] | None:
    rows = get_default_repository().list_online_decisions(limit=5000)
    for row in rows:
        if int(row.get("id") or -1) == int(decision_id):
            return row
    return None
