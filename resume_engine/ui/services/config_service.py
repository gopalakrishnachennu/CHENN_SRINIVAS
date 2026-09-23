"""Dynamic UI configuration service with SAFE / ADVANCED / LOCKED classes."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any

from resume_engine.config import thresholds
from resume_engine.learning.online import config as online_config
from resume_engine.ui.db import connect_ui_db, ensure_ui_schema
from resume_engine.ui.services.audit_service import record_audit_event

# classification: SAFE | ADVANCED | LOCKED
SETTING_SPECS: dict[str, dict[str, Any]] = {
    "default_variant_count": {
        "classification": "SAFE",
        "type": "int",
        "default": thresholds.DEFAULT_VARIANT_COUNT,
        "min": 1,
        "max": 10,
    },
    "default_openai_model": {
        "classification": "SAFE",
        "type": "str",
        "default": os.getenv("OPENAI_MODEL", "gpt-5.6"),
    },
    "laya_default_enabled": {
        "classification": "SAFE",
        "type": "bool",
        "default": True,
    },
    "repair_default_enabled": {
        "classification": "SAFE",
        "type": "bool",
        "default": True,
    },
    "default_export_docx": {
        "classification": "SAFE",
        "type": "bool",
        "default": True,
    },
    "default_export_pdf": {
        "classification": "SAFE",
        "type": "bool",
        "default": True,
    },
    "default_document_template": {
        "classification": "SAFE",
        "type": "str",
        "default": "classic_ats",
    },
    "pass_score_min": {
        "classification": "ADVANCED",
        "type": "float",
        "default": thresholds.PASS_SCORE_MIN,
        "min": 0.0,
        "max": 100.0,
    },
    "p1_coverage_min": {
        "classification": "ADVANCED",
        "type": "float",
        "default": thresholds.P1_COVERAGE_MIN,
        "min": 0.0,
        "max": 1.0,
    },
    "p2_coverage_min": {
        "classification": "ADVANCED",
        "type": "float",
        "default": thresholds.P2_COVERAGE_MIN,
        "min": 0.0,
        "max": 1.0,
    },
    "p4_usage_max": {
        "classification": "ADVANCED",
        "type": "float",
        "default": thresholds.P4_USAGE_MAX,
        "min": 0.0,
        "max": 1.0,
    },
    "variant_similarity_max": {
        "classification": "ADVANCED",
        "type": "float",
        "default": thresholds.VARIANT_SIMILARITY_MAX,
        "min": 0.0,
        "max": 1.0,
    },
    "cross_run_similarity_max": {
        "classification": "ADVANCED",
        "type": "float",
        "default": thresholds.CROSS_RUN_SIMILARITY_MAX,
        "min": 0.0,
        "max": 1.0,
    },
    "variant_regen_max": {
        "classification": "ADVANCED",
        "type": "int",
        "default": thresholds.VARIANT_REGEN_MAX,
        "min": 0,
        "max": 5,
    },
    "learning_min_sample_count": {
        "classification": "ADVANCED",
        "type": "int",
        "default": thresholds.LEARNING_MIN_SAMPLE_COUNT,
        "min": 1,
        "max": 1000,
    },
    "online_min_total_observations": {
        "classification": "ADVANCED",
        "type": "int",
        "default": online_config.ONLINE_MIN_TOTAL_OBSERVATIONS,
        "min": 1,
        "max": 100000,
    },
    "online_min_action_observations": {
        "classification": "ADVANCED",
        "type": "int",
        "default": online_config.ONLINE_MIN_ACTION_OBSERVATIONS,
        "min": 1,
        "max": 10000,
    },
    "hybrid_probability_min": {
        "classification": "ADVANCED",
        "type": "float",
        "default": thresholds.LEARNING_HYBRID_PROBABILITY_MIN,
        "min": 0.0,
        "max": 1.0,
    },
    # LOCKED — display only; mutations rejected
    "technology_firewall_enabled": {
        "classification": "LOCKED",
        "type": "bool",
        "default": True,
    },
    "candidate_truthfulness_enforced": {
        "classification": "LOCKED",
        "type": "bool",
        "default": True,
    },
    "river_active_mode_enabled": {
        "classification": "LOCKED",
        "type": "bool",
        "default": False,
    },
}


class ConfigValidationError(ValueError):
    pass


class ConfigLockedError(PermissionError):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _coerce(spec: dict[str, Any], raw: Any) -> Any:
    kind = spec["type"]
    if kind == "bool":
        if isinstance(raw, bool):
            return raw
        text = str(raw).strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
        raise ConfigValidationError(f"invalid bool: {raw!r}")
    if kind == "int":
        value = int(raw)
        if "min" in spec and value < spec["min"]:
            raise ConfigValidationError(f"below min {spec['min']}")
        if "max" in spec and value > spec["max"]:
            raise ConfigValidationError(f"above max {spec['max']}")
        return value
    if kind == "float":
        value = float(raw)
        if "min" in spec and value < spec["min"]:
            raise ConfigValidationError(f"below min {spec['min']}")
        if "max" in spec and value > spec["max"]:
            raise ConfigValidationError(f"above max {spec['max']}")
        return value
    return str(raw)


def _env_override(key: str) -> Any | None:
    env_key = f"RESUME_UI_{key.upper()}"
    if env_key not in os.environ:
        return None
    return os.environ[env_key]


def get_effective_setting(key: str) -> Any:
    if key not in SETTING_SPECS:
        raise KeyError(key)
    spec = SETTING_SPECS[key]
    # Priority: code default → env → saved UI config
    value = spec["default"]
    env_val = _env_override(key)
    if env_val is not None:
        try:
            value = _coerce(spec, env_val)
        except ConfigValidationError:
            pass
    ensure_ui_schema()
    with connect_ui_db() as conn:
        row = conn.execute("SELECT value FROM ui_config WHERE key = ?", (key,)).fetchone()
        if row is not None:
            try:
                value = _coerce(spec, json.loads(row["value"]))
            except (ConfigValidationError, json.JSONDecodeError):
                pass
    return value


def list_settings() -> list[dict[str, Any]]:
    items = []
    for key, spec in SETTING_SPECS.items():
        items.append(
            {
                "key": key,
                "classification": spec["classification"],
                "type": spec["type"],
                "default": spec["default"],
                "value": get_effective_setting(key),
                "locked": spec["classification"] == "LOCKED",
            }
        )
    return items


def set_setting(
    key: str,
    new_value: Any,
    *,
    actor: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    if key not in SETTING_SPECS:
        raise KeyError(key)
    spec = SETTING_SPECS[key]
    if spec["classification"] == "LOCKED":
        raise ConfigLockedError(f"setting locked: {key}")
    coerced = _coerce(spec, new_value)
    old = get_effective_setting(key)
    ensure_ui_schema()
    with connect_ui_db() as conn:
        conn.execute(
            """
            INSERT INTO ui_config(key, value, classification, updated_at, updated_by)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
              value=excluded.value,
              classification=excluded.classification,
              updated_at=excluded.updated_at,
              updated_by=excluded.updated_by
            """,
            (key, json.dumps(coerced), spec["classification"], _now(), actor),
        )
        conn.execute(
            """
            INSERT INTO ui_config_versions(key, old_value, new_value, actor, reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                key,
                json.dumps(old),
                json.dumps(coerced),
                actor,
                reason,
                _now(),
            ),
        )
        conn.commit()
    record_audit_event(
        action="settings.change",
        actor=actor,
        entity_type="ui_config",
        entity_id=key,
        old_value=old,
        new_value=coerced,
        metadata={"reason": reason},
    )
    return {"key": key, "old_value": old, "new_value": coerced}


def get_configuration_versions(key: str | None = None, *, limit: int = 100) -> list[dict]:
    ensure_ui_schema()
    with connect_ui_db() as conn:
        if key:
            rows = conn.execute(
                """
                SELECT * FROM ui_config_versions
                WHERE key = ?
                ORDER BY id DESC LIMIT ?
                """,
                (key, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM ui_config_versions ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]


def rollback_configuration(
    version_id: int,
    *,
    actor: str | None = None,
) -> dict[str, Any]:
    ensure_ui_schema()
    with connect_ui_db() as conn:
        row = conn.execute(
            "SELECT * FROM ui_config_versions WHERE id = ?",
            (version_id,),
        ).fetchone()
    if row is None:
        raise KeyError(f"config version {version_id}")
    key = row["key"]
    old_value = json.loads(row["old_value"]) if row["old_value"] is not None else None
    return set_setting(key, old_value, actor=actor, reason=f"rollback:{version_id}")
