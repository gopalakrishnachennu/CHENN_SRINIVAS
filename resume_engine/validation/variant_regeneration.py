"""Cross-variant duplication correction: regenerate only the weaker variant."""

from __future__ import annotations

from itertools import combinations

from resume_engine.config import thresholds
from resume_engine.models.resume_schema import ResumeJSON
from resume_engine.models.resume_strategy import VariantStrategy
from resume_engine.validation.text_utils import flatten_resume_text, similarity


def variant_focus_score(resume: ResumeJSON, variant: VariantStrategy) -> float:
    """How well the resume text embodies the assigned angle emphasis terms."""
    text = flatten_resume_text(resume).lower()
    if not variant.emphasis:
        return 0.0
    ranked = sorted(variant.emphasis.items(), key=lambda item: -item[1])[:8]
    hits = 0
    for skill, weight in ranked:
        if weight >= 0.9 and skill.lower() in text:
            hits += 1
    return round(100.0 * hits / max(1, len(ranked)), 2)


def choose_weaker_variant(
    left: ResumeJSON,
    right: ResumeJSON,
    left_score: float,
    right_score: float,
    left_variant: VariantStrategy | None = None,
    right_variant: VariantStrategy | None = None,
) -> str:
    """Return variant_id of the weaker resume."""
    left_focus = variant_focus_score(left, left_variant) if left_variant else 0.0
    right_focus = variant_focus_score(right, right_variant) if right_variant else 0.0

    left_rank = (left_score, left_focus)
    right_rank = (right_score, right_focus)
    if left_rank <= right_rank:
        return left.variant_id or "unknown_left"
    return right.variant_id or "unknown_right"


def find_duplicate_pairs(
    resumes: list[ResumeJSON],
    scores: dict[str, float],
    variants: dict[str, VariantStrategy] | None = None,
    threshold: float | None = None,
) -> list[dict]:
    limit = threshold if threshold is not None else thresholds.VARIANT_SIMILARITY_MAX
    pairs = []
    for left, right in combinations(resumes, 2):
        left_id = left.variant_id or "unknown_left"
        right_id = right.variant_id or "unknown_right"
        ratio = similarity(flatten_resume_text(left), flatten_resume_text(right))
        if ratio < limit:
            continue
        weaker = choose_weaker_variant(
            left,
            right,
            scores.get(left_id, 0.0),
            scores.get(right_id, 0.0),
            (variants or {}).get(left_id),
            (variants or {}).get(right_id),
        )
        pairs.append(
            {
                "left": left_id,
                "right": right_id,
                "similarity": ratio,
                "weaker_variant_id": weaker,
            }
        )
    return pairs
