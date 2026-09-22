from resume_engine.config import thresholds
from resume_engine.models.jd_blueprint import JDBlueprint
from resume_engine.models.resume_schema import ResumeJSON
from resume_engine.models.validation_schema import ValidationIssue, ValidatorResult
from resume_engine.validation.text_utils import all_bullets


def _answer_noul(answer: dict) -> float:
    return float(answer.get("noul", answer.get("probability", answer.get("value", 0.0))))


def _predict_with_retries(laya_agent, state: dict, questions: dict) -> dict:
    last_error: Exception | None = None
    attempts = max(1, thresholds.LAYA_BATCH_MAX_RETRIES + 1)
    for _ in range(attempts):
        try:
            result = laya_agent.predict(state, questions)
            if not isinstance(result, dict) or "answers" not in result:
                raise RuntimeError("Laya predict returned malformed payload.")
            return result
        except Exception as exc:  # noqa: BLE001 - classified below
            last_error = exc
    raise RuntimeError(f"Laya batch failed after retries: {last_error}")


def build_laya_responsibility_payload(
    blueprint: JDBlueprint,
    *,
    uncovered_ids: list[str] | None = None,
    max_items: int | None = None,
) -> dict:
    """
    Gate 2: feed Laya structured responsibilities with a budget.

    Prefer uncovered responsibility IDs (from keyword validator) first, then
    remaining entries in JD order. Never silently hard-cap at 8.
    """
    budget = max_items if max_items is not None else thresholds.LAYA_RESPONSIBILITY_MAX
    entries = blueprint.responsibility_entries()
    total = len(entries)
    uncovered = set(uncovered_ids or [])

    ordered: list[dict[str, str]] = []
    if uncovered:
        for entry in entries:
            if entry["id"] in uncovered:
                ordered.append(entry)
    for entry in entries:
        if entry not in ordered:
            ordered.append(entry)

    selected = ordered[: max(0, budget)] if budget >= 0 else ordered
    truncated = len(selected) < total
    return {
        "responsibilities": [item["text"] for item in selected],
        "responsibility_entries": selected,
        "responsibilities_total": total,
        "responsibilities_in_state": len(selected),
        "responsibilities_truncated": truncated,
        "uncovered_responsibility_ids": sorted(uncovered),
    }


def validate_with_laya(
    blueprint: JDBlueprint,
    resume: ResumeJSON,
    laya_agent,
    *,
    uncovered_responsibility_ids: list[str] | None = None,
) -> ValidatorResult:
    bullets = all_bullets(resume)
    if not bullets:
        return ValidatorResult(
            name="laya_validator",
            passed=False,
            score=0.0,
            issues=[
                ValidationIssue(
                    code="FAIL_NO_BULLETS_FOR_LAYA",
                    severity="error",
                    message="Resume has no bullets for Laya semantic validation.",
                )
            ],
        )

    responsibility_payload = build_laya_responsibility_payload(
        blueprint,
        uncovered_ids=uncovered_responsibility_ids,
    )
    state = {
        "target_role": blueprint.job.target_title,
        "primary_family": blueprint.job.primary_family,
        "secondary_family": blueprint.job.secondary_family,
        "seniority": blueprint.job.seniority,
        "p1": blueprint.priority_skills.get("P1", []),
        "p2": blueprint.priority_skills.get("P2", []),
        "responsibilities": responsibility_payload["responsibilities"],
        "responsibility_entries": responsibility_payload["responsibility_entries"],
    }

    batch_size = max(1, thresholds.LAYA_BULLET_BATCH_SIZE)
    issues: list[ValidationIssue] = []
    alignment_scores: list[float] = []
    batch_count = 0
    validated = 0

    for start in range(0, len(bullets), batch_size):
        batch = bullets[start : start + batch_size]
        batch_count += 1
        questions = {}
        for offset, (_, bullet) in enumerate(batch):
            questions[f"bullet_{offset}_aligned"] = {
                "type": "noul",
                "instructions": (
                    "Does this resume bullet semantically align to the target role, seniority, "
                    "primary/secondary job family, and JD responsibilities? "
                    f"Bullet: {bullet}"
                ),
            }
            questions[f"bullet_{offset}_generic"] = {
                "type": "noul",
                "instructions": (
                    f"Is this bullet overly generic and likely needing rewrite? Bullet: {bullet}"
                ),
            }

        try:
            result = _predict_with_retries(laya_agent, state, questions)
        except Exception as exc:  # noqa: BLE001
            return ValidatorResult(
                name="laya_validator",
                passed=False,
                score=0.0,
                issues=[
                    ValidationIssue(
                        code="FAIL_LAYA_BATCH",
                        severity="error",
                        message=f"Laya batch {batch_count} failed and was not treated as pass: {exc}",
                        metadata={"batch_index": batch_count, "batch_size": len(batch)},
                    )
                ],
                details={
                    "validated_bullet_count": validated,
                    "total_bullet_count": len(bullets),
                    "batch_count": batch_count,
                    "failed_batch": True,
                },
            )

        for offset, (location, bullet) in enumerate(batch):
            aligned = _answer_noul(result["answers"][f"bullet_{offset}_aligned"])
            generic = _answer_noul(result["answers"][f"bullet_{offset}_generic"])
            alignment_scores.append(aligned)
            validated += 1

            if aligned < thresholds.BULLET_RELEVANCE_MIN:
                issues.append(
                    ValidationIssue(
                        code="WARN_LAYA_LOW_RELEVANCE",
                        severity="warning",
                        message=f"Laya scored bullet relevance low ({aligned:.2f}).",
                        location=location,
                        repair_hint="Rewrite bullet to better match target role and JD responsibilities.",
                        metadata={"bullet": bullet, "alignment": aligned},
                    )
                )
            if generic >= 0.70:
                issues.append(
                    ValidationIssue(
                        code="WARN_LAYA_GENERIC_BULLET",
                        severity="warning",
                        message=f"Laya found bullet likely generic ({generic:.2f}).",
                        location=location,
                        repair_hint="Rewrite bullet with more specific technology, action, and result.",
                        metadata={"bullet": bullet, "generic_probability": generic},
                    )
                )

    avg_score = sum(alignment_scores) / max(1, len(alignment_scores))
    return ValidatorResult(
        name="laya_validator",
        passed=avg_score >= thresholds.ROLE_ALIGNMENT_MIN,
        score=round(avg_score * 100, 2),
        issues=issues,
        details={
            "average_semantic_alignment": avg_score,
            "validated_bullet_count": validated,
            "total_bullet_count": len(bullets),
            "batch_count": batch_count,
            "batch_size": batch_size,
            "failed_batch": False,
            "responsibilities_total": responsibility_payload["responsibilities_total"],
            "responsibilities_in_state": responsibility_payload["responsibilities_in_state"],
            "responsibilities_truncated": responsibility_payload["responsibilities_truncated"],
            "uncovered_responsibility_ids": responsibility_payload["uncovered_responsibility_ids"],
        },
    )
