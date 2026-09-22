"""Strategy memory: summarize, retrieve, and rank from eligible outcomes only."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from resume_engine.config import thresholds
from resume_engine.config.settings import LEARNING_STORAGE_DIR
from resume_engine.learning.eligibility import (
    is_hybrid_blueprint,
    is_record_eligible_for_learning,
)
from resume_engine.learning.outcome_store import OUTCOMES_FILE
from resume_engine.models.jd_blueprint import JDBlueprint


def load_outcome_records(path: Path | None = None) -> list[dict]:
    outcomes_path = path or OUTCOMES_FILE
    if not outcomes_path.exists():
        return []
    records: list[dict] = []
    with open(outcomes_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records


def _record_score(record: dict) -> float:
    for key in ("score_after", "score_after_repair", "JD_COMPATIBILITY_SCORE", "score_before_repair"):
        value = record.get(key)
        if value is not None:
            return float(value)
    return 0.0


def blueprint_learning_scope(blueprint: JDBlueprint) -> dict[str, Any]:
    return {
        "primary_family": blueprint.job.primary_family,
        "secondary_family": blueprint.job.secondary_family,
        "hybrid": is_hybrid_blueprint(
            blueprint.job.secondary_family,
            blueprint.job.hybrid_probability,
        ),
        "seniority": blueprint.job.seniority,
    }


def matches_learning_scope(record: dict, scope: dict[str, Any]) -> bool:
    record_hybrid = record.get("hybrid")
    if record_hybrid is None:
        record_hybrid = is_hybrid_blueprint(
            record.get("secondary_family"),
            record.get("hybrid_probability"),
        )
    return (
        record.get("primary_family") == scope["primary_family"]
        and (record.get("secondary_family") or "none") == scope["secondary_family"]
        and bool(record_hybrid) == bool(scope["hybrid"])
        and (record.get("seniority") or "") == scope["seniority"]
    )


def retrieve_eligible_history(
    blueprint: JDBlueprint,
    *,
    outcomes_path: Path | None = None,
) -> list[dict]:
    """Historical successful outcomes matching family / hybrid / seniority scope."""
    scope = blueprint_learning_scope(blueprint)
    return [
        record
        for record in load_outcome_records(outcomes_path)
        if matches_learning_scope(record, scope) and is_record_eligible_for_learning(record)
    ]


def positioning_performance(
    records: list[dict],
) -> dict[str, dict[str, float | int]]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for record in records:
        positioning = record.get("variant_positioning")
        if not positioning:
            continue
        grouped[str(positioning)].append(_record_score(record))

    summary: dict[str, dict[str, float | int]] = {}
    for positioning, scores in grouped.items():
        summary[positioning] = {
            "average_score": round(sum(scores) / len(scores), 2),
            "count": len(scores),
        }
    return summary


def retrieve_strategy_insights(
    blueprint: JDBlueprint,
    *,
    outcomes_path: Path | None = None,
    min_samples: int | None = None,
) -> dict[str, Any]:
    """
    Retrieve ranking insights for a blueprint.

    Returns applied=False when eligible sample count < LEARNING_MIN_SAMPLE_COUNT.
    Never invents technologies; callers may only re-rank existing angles.
    """
    minimum = min_samples if min_samples is not None else thresholds.LEARNING_MIN_SAMPLE_COUNT
    eligible = retrieve_eligible_history(blueprint, outcomes_path=outcomes_path)
    by_positioning = positioning_performance(eligible)
    applied = len(eligible) >= minimum
    return {
        "applied": applied,
        "eligible_sample_count": len(eligible),
        "min_sample_count": minimum,
        "scope": blueprint_learning_scope(blueprint),
        "positioning_scores": by_positioning if applied else {},
        "historical_weight": thresholds.LEARNING_HISTORICAL_WEIGHT if applied else 0.0,
    }


def historical_boost_for_positioning(insights: dict[str, Any], positioning: str) -> float:
    if not insights.get("applied"):
        return 0.0
    stats = (insights.get("positioning_scores") or {}).get(positioning)
    if not stats:
        return 0.0
    average = float(stats["average_score"])
    weight = float(insights.get("historical_weight") or thresholds.LEARNING_HISTORICAL_WEIGHT)
    # Map score ~0-100 into a ranking boost; high historical averages rise first.
    return (average / 100.0) * weight


def summarize_strategy_memory(*, eligible_only: bool = True) -> dict:
    records = load_outcome_records()
    if eligible_only:
        records = [record for record in records if is_record_eligible_for_learning(record)]

    grouped: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    for record in records:
        key = (
            str(record.get("primary_family", "unknown")),
            str(record.get("secondary_family", "none")),
            str(record.get("variant_positioning", "unknown")),
        )
        grouped[key].append(_record_score(record))

    summary = {}
    for key, scores in grouped.items():
        summary["|".join(key)] = {
            "average_score": round(sum(scores) / len(scores), 2),
            "count": len(scores),
            "eligible_only": eligible_only,
        }
    return summary


def save_strategy_memory_summary() -> Path:
    LEARNING_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    path = LEARNING_STORAGE_DIR / "strategy_memory_summary.json"
    payload = {
        "eligible": summarize_strategy_memory(eligible_only=True),
        "all_records": summarize_strategy_memory(eligible_only=False),
        "learning_min_sample_count": thresholds.LEARNING_MIN_SAMPLE_COUNT,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    try:
        from resume_engine.learning.repository import get_default_repository

        get_default_repository().save_strategy_memory_snapshot(payload.get("eligible") or {})
    except Exception:
        pass
    return path
