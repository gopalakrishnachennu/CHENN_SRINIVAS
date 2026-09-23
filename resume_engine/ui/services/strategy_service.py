"""Strategy center — eligible positionings only; no tech invention."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from resume_engine.models.jd_blueprint import JDBlueprint
from resume_engine.strategy.variant_planner import (
    ANGLE_LIBRARY,
    list_all_candidate_positionings,
    list_eligible_positionings,
)


def load_blueprint_obj(path: str | Path) -> JDBlueprint:
    return JDBlueprint.from_json_file(str(path))


def strategy_overview(blueprint_path: str | Path) -> dict[str, Any]:
    blueprint = load_blueprint_obj(blueprint_path)
    eligible = list_eligible_positionings(blueprint)
    all_candidates = list_all_candidate_positionings(blueprint)
    angles = {a.positioning: a for a in ANGLE_LIBRARY}
    strategies = []
    for i, name in enumerate(all_candidates, 1):
        angle = angles.get(name)
        strategies.append({
            "positioning": name,
            "description": getattr(angle, "description", None) if angle else None,
            "family": (", ".join(angle.families) if angle else None),
            "eligible": name in eligible,
            "production_rank": i if name in eligible else None,
            "shadow_rank": None,
            "evidence_score": None,
            "historical_score": None,
            "river_shadow_score": None,
        })
    job = blueprint.job
    return {
        "primary_family": getattr(job, "primary_family", None),
        "secondary_family": getattr(job, "secondary_family", None),
        "hybrid_probability": getattr(job, "hybrid_probability", None),
        "eligible": eligible,
        "all_candidates": all_candidates,
        "strategies": strategies,
    }


def filter_manual_order(requested: list[str], blueprint_path: str | Path) -> list[str]:
    """Only keep positionings that are production-eligible."""
    overview = strategy_overview(blueprint_path)
    allowed = set(overview["all_candidates"])
    return [name for name in requested if name in allowed]
