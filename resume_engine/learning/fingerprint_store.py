"""Cross-run resume fingerprint storage and similarity checks."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from resume_engine.config import thresholds
from resume_engine.config.settings import LEARNING_STORAGE_DIR, ensure_storage_dirs, portable_path
from resume_engine.models.resume_schema import ResumeJSON
from resume_engine.models.validation_schema import ValidationIssue, ValidatorResult
from resume_engine.validation.text_utils import flatten_resume_text, normalize_text, similarity


FINGERPRINTS_FILE = LEARNING_STORAGE_DIR / "resume_fingerprints.jsonl"


def content_fingerprint(resume: ResumeJSON) -> str:
    text = normalize_text(flatten_resume_text(resume))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def save_fingerprint(
    *,
    jd_hash: str,
    run_id: str,
    variant_id: str,
    resume: ResumeJSON,
    passed: bool,
) -> Path:
    ensure_storage_dirs()
    record = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "jd_hash": jd_hash,
        "run_id": run_id,
        "variant_id": variant_id,
        "passed": passed,
        "normalized_text_hash": content_fingerprint(resume),
        "text_preview": normalize_text(flatten_resume_text(resume))[:240],
    }
    from resume_engine.learning.repository import get_default_repository

    get_default_repository().save_fingerprint(record)
    return FINGERPRINTS_FILE


def _load_fingerprints_jsonl(jd_hash: str, exclude_run_id: str | None = None) -> list[dict]:
    if not FINGERPRINTS_FILE.exists():
        return []
    records = []
    with open(FINGERPRINTS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("jd_hash") != jd_hash:
                continue
            if not record.get("passed"):
                continue
            if exclude_run_id and record.get("run_id") == exclude_run_id:
                continue
            records.append(record)
    return records


def load_prior_successful_fingerprints(jd_hash: str, exclude_run_id: str | None = None) -> list[dict]:
    # Prefer SQLite when available; fall back to legacy JSONL.
    try:
        from resume_engine.learning.repository import get_default_repository

        prior = get_default_repository().get_prior_variants(
            jd_hash,
            exclude_run_id=exclude_run_id,
            passed_only=True,
        )
        if prior:
            return prior
    except Exception:
        pass
    return _load_fingerprints_jsonl(jd_hash, exclude_run_id=exclude_run_id)


def validate_cross_run_uniqueness(
    resume: ResumeJSON,
    jd_hash: str,
    run_id: str,
    threshold: float | None = None,
) -> ValidatorResult:
    """
    Compare against prior successful variants for the same JD.
    Uniqueness must never invent technologies; it only flags narrative duplication.
    """
    limit = threshold if threshold is not None else thresholds.CROSS_RUN_SIMILARITY_MAX
    current_text = flatten_resume_text(resume)
    issues: list[ValidationIssue] = []
    comparisons = []

    for prior in load_prior_successful_fingerprints(jd_hash, exclude_run_id=run_id):
        prior_preview = prior.get("text_preview", "")
        # Prefer hash short-circuit, then preview similarity (full prior text not stored for privacy).
        if prior.get("normalized_text_hash") == content_fingerprint(resume):
            ratio = 1.0
        else:
            ratio = similarity(current_text, prior_preview)
        comparisons.append(
            {
                "prior_run_id": prior.get("run_id"),
                "prior_variant_id": prior.get("variant_id"),
                "similarity": round(ratio, 4),
            }
        )
        if ratio >= limit:
            issues.append(
                ValidationIssue(
                    code="FAIL_CROSS_RUN_DUPLICATION",
                    severity="error",
                    message=(
                        f"Variant too similar to prior successful run "
                        f"{prior.get('run_id')}/{prior.get('variant_id')} ({ratio:.2f})."
                    ),
                    repair_hint=(
                        "Regenerate narrative/bullet structure while retaining required JD coverage."
                    ),
                    metadata={
                        "similarity": ratio,
                        "prior_run_id": prior.get("run_id"),
                        "prior_variant_id": prior.get("variant_id"),
                        "fingerprint_store": portable_path(FINGERPRINTS_FILE),
                    },
                )
            )

    return ValidatorResult(
        name="cross_run_uniqueness_validator",
        passed=not issues,
        score=100.0 if not issues else max(0.0, 100.0 - 25 * len(issues)),
        issues=issues,
        details={"comparisons": comparisons, "threshold": limit},
    )
