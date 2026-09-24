"""Shared schema helpers for Phase 3.3 JD intelligence."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

JOB_INTELLIGENCE_SCHEMA_VERSION = "job-intelligence-v1"

STATUS_EXPLICIT = "EXPLICIT"
STATUS_INFERRED = "INFERRED"
STATUS_NOT_STATED = "NOT_STATED"
STATUS_AMBIGUOUS = "AMBIGUOUS"
STATUS_MANUAL_OVERRIDE = "MANUAL_OVERRIDE"

SOURCE_DETERMINISTIC = "DETERMINISTIC"
SOURCE_OPENAI = "OPENAI"
SOURCE_LAYA = "LAYA"
SOURCE_MANUAL = "MANUAL"


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def field(
    value: Any,
    *,
    status: str = STATUS_EXPLICIT,
    source: str = SOURCE_DETERMINISTIC,
    evidence: str | list[str] | None = None,
    confidence: float | None = None,
    manual_override: bool = False,
) -> dict[str, Any]:
    if evidence is None:
        items: list[str] = []
    elif isinstance(evidence, str):
        items = [evidence]
    else:
        items = [str(item) for item in evidence if str(item).strip()]
    return {
        "value": value,
        "status": status,
        "source": source,
        "evidence": items,
        "confidence": confidence,
        "manual_override": manual_override,
    }


def not_stated(value: Any = None, *, source: str = SOURCE_DETERMINISTIC) -> dict[str, Any]:
    return field(value, status=STATUS_NOT_STATED, source=source, evidence=[])


def unknown(value: str = "UNKNOWN") -> dict[str, Any]:
    return field(value, status=STATUS_NOT_STATED, evidence=[])


def raw_value(value: Any) -> Any:
    if isinstance(value, dict) and "value" in value:
        return value.get("value")
    return value


def build_base_intelligence(raw_jd_text: str, raw_jd_hash: str) -> dict[str, Any]:
    return {
        "schema_version": JOB_INTELLIGENCE_SCHEMA_VERSION,
        "analysis_version": 1,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "raw_jd_hash": raw_jd_hash,
        "raw_jd_text": raw_jd_text,
        "parser_warnings": [],
        "classification_conflicts": [],
        "manual_overrides": [],
        "quality_flags": [],
        "openai_extraction": {},
        "laya_output": {},
    }
