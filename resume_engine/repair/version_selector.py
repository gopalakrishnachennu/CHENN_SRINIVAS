"""Resume version selection after optional repair (Wave 1)."""

from __future__ import annotations

from dataclasses import dataclass, field

from resume_engine.models.resume_schema import ResumeJSON
from resume_engine.models.validation_schema import ValidationBundle, ValidationIssue, ValidatorResult


@dataclass
class VersionSelection:
    resume: ResumeJSON | None
    bundle: ValidationBundle
    stage: str  # "raw" | "repaired" | "none"
    status: str  # VALIDATED | FAILED_VALIDATION
    regression_recorded: bool = False
    notes: list[str] = field(default_factory=list)


def _record_score_regression(
    repaired_bundle: ValidationBundle,
    score_before: float,
    score_after: float,
) -> None:
    repaired_bundle.validator_results.append(
        ValidatorResult(
            name="repair_score_guard",
            passed=True,  # informational warning; selection logic owns promotion
            score=score_after,
            issues=[
                ValidationIssue(
                    code="REPAIR_SCORE_REGRESSION",
                    severity="warning",
                    message=(
                        f"Repair score declined from {score_before:.2f} to {score_after:.2f}."
                    ),
                    metadata={
                        "score_before": score_before,
                        "score_after": score_after,
                    },
                )
            ],
            details={
                "score_before": score_before,
                "score_after": score_after,
            },
        )
    )


def select_best_resume_version(
    raw_resume: ResumeJSON,
    raw_bundle: ValidationBundle,
    repaired_resume: ResumeJSON | None,
    repaired_bundle: ValidationBundle | None,
) -> VersionSelection:
    """
    Selection rules:
    1. Passing version always beats failing version.
    2. If both pass, use the higher valid score.
    3. If both fail, neither may become final.
    4. If score_after < score_before, record REPAIR_SCORE_REGRESSION.
    """
    notes: list[str] = []
    regression = False

    if repaired_resume is None or repaired_bundle is None:
        if raw_bundle.passed:
            return VersionSelection(
                resume=raw_resume,
                bundle=raw_bundle,
                stage="raw",
                status="VALIDATED",
                notes=["No repair performed; raw version passed."],
            )
        return VersionSelection(
            resume=None,
            bundle=raw_bundle,
            stage="none",
            status="FAILED_VALIDATION",
            notes=["No repair performed; raw version failed."],
        )

    score_before = raw_bundle.optimization_score
    score_after = repaired_bundle.optimization_score
    if score_after < score_before:
        regression = True
        notes.append("REPAIR_SCORE_REGRESSION")
        _record_score_regression(repaired_bundle, score_before, score_after)

    raw_pass = raw_bundle.passed
    repaired_pass = repaired_bundle.passed

    if raw_pass and not repaired_pass:
        notes.append("Kept raw: repaired failed while raw passed.")
        return VersionSelection(
            resume=raw_resume,
            bundle=raw_bundle,
            stage="raw",
            status="VALIDATED",
            regression_recorded=regression,
            notes=notes,
        )

    if repaired_pass and not raw_pass:
        notes.append("Selected repaired: only repaired version passed.")
        return VersionSelection(
            resume=repaired_resume,
            bundle=repaired_bundle,
            stage="repaired",
            status="VALIDATED",
            regression_recorded=regression,
            notes=notes,
        )

    if raw_pass and repaired_pass:
        if score_after >= score_before:
            notes.append("Selected repaired: both passed; repaired score >= raw score.")
            return VersionSelection(
                resume=repaired_resume,
                bundle=repaired_bundle,
                stage="repaired",
                status="VALIDATED",
                regression_recorded=regression,
                notes=notes,
            )
        notes.append("Kept raw: both passed; repaired score regressed.")
        return VersionSelection(
            resume=raw_resume,
            bundle=raw_bundle,
            stage="raw",
            status="VALIDATED",
            regression_recorded=regression,
            notes=notes,
        )

    notes.append("Both raw and repaired failed; no final promotion.")
    # Keep the higher-scoring failed artifact in rejected/ for forensics.
    prefer_repaired = score_after >= score_before
    return VersionSelection(
        resume=repaired_resume if prefer_repaired else raw_resume,
        bundle=repaired_bundle if prefer_repaired else raw_bundle,
        stage="repaired" if prefer_repaired else "raw",
        status="FAILED_VALIDATION",
        regression_recorded=regression,
        notes=notes,
    )
