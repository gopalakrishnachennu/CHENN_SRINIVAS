"""Cross-run resume fingerprint storage and similarity checks (Gate 2)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from resume_engine.config import thresholds
from resume_engine.config.settings import LEARNING_STORAGE_DIR, ensure_storage_dirs, portable_path
from resume_engine.learning.fingerprint_signatures import (
    compute_minhash,
    compute_simhash64,
    signature_near_duplicate,
)
from resume_engine.models.resume_schema import ResumeJSON
from resume_engine.models.validation_schema import ValidationIssue, ValidatorResult
from resume_engine.validation.text_utils import flatten_resume_text, normalize_text, similarity


FINGERPRINTS_FILE = LEARNING_STORAGE_DIR / "resume_fingerprints.jsonl"
PREVIEW_LEN = 240


def content_fingerprint(resume: ResumeJSON) -> str:
    text = normalize_text(flatten_resume_text(resume))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_fingerprint_record(
    *,
    jd_hash: str,
    run_id: str,
    variant_id: str,
    resume: ResumeJSON,
    passed: bool,
) -> dict:
    normalized = normalize_text(flatten_resume_text(resume))
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "jd_hash": jd_hash,
        "run_id": run_id,
        "variant_id": variant_id,
        "passed": passed,
        "normalized_text_hash": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        "text_preview": normalized[:PREVIEW_LEN],
        "simhash64": compute_simhash64(normalized),
        "minhash": compute_minhash(normalized),
        "signature_version": 2,
    }


def save_fingerprint(
    *,
    jd_hash: str,
    run_id: str,
    variant_id: str,
    resume: ResumeJSON,
    passed: bool,
) -> Path:
    ensure_storage_dirs()
    record = build_fingerprint_record(
        jd_hash=jd_hash,
        run_id=run_id,
        variant_id=variant_id,
        resume=resume,
        passed=passed,
    )
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


def _compare_to_prior(current_text: str, current_record: dict, prior: dict) -> tuple[float, dict]:
    """
    Similarity against a prior fingerprint.

    Prefer exact SHA256, then SimHash/MinHash signatures, then preview↔preview
    SequenceMatcher (never full-text vs truncated preview alone).
    """
    diagnostics: dict = {"method": "none"}
    if prior.get("normalized_text_hash") == current_record["normalized_text_hash"]:
        diagnostics["method"] = "sha256"
        return 1.0, diagnostics

    prior_sim = prior.get("simhash64")
    prior_mh = prior.get("minhash")
    near, sig_diag = signature_near_duplicate(
        current_simhash=int(current_record["simhash64"]),
        prior_simhash=int(prior_sim) if prior_sim is not None else None,
        current_minhash=list(current_record["minhash"]),
        prior_minhash=list(prior_mh) if prior_mh else None,
    )
    diagnostics.update(sig_diag)

    preview_ratio = similarity(
        current_record.get("text_preview", ""),
        prior.get("text_preview", ""),
    )
    diagnostics["preview_similarity"] = round(preview_ratio, 4)

    if near:
        # Map signature near-duplicate onto a ratio at/above the cross-run threshold.
        ratio = max(
            thresholds.CROSS_RUN_SIMILARITY_MAX,
            float(sig_diag.get("simhash_similarity") or 0.0),
            float(sig_diag.get("minhash_jaccard") or 0.0),
            preview_ratio,
        )
        diagnostics["method"] = "signature"
        return min(1.0, ratio), diagnostics

    # Legacy fingerprints without signatures: preview↔preview only (symmetric).
    diagnostics["method"] = "preview"
    return preview_ratio, diagnostics


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
    current_record = build_fingerprint_record(
        jd_hash=jd_hash,
        run_id=run_id,
        variant_id=resume.variant_id or "unknown",
        resume=resume,
        passed=True,
    )
    issues: list[ValidationIssue] = []
    comparisons = []

    for prior in load_prior_successful_fingerprints(jd_hash, exclude_run_id=run_id):
        ratio, diagnostics = _compare_to_prior(
            flatten_resume_text(resume),
            current_record,
            prior,
        )
        comparisons.append(
            {
                "prior_run_id": prior.get("run_id"),
                "prior_variant_id": prior.get("variant_id"),
                "similarity": round(ratio, 4),
                **diagnostics,
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
                        **diagnostics,
                    },
                )
            )

    return ValidatorResult(
        name="cross_run_uniqueness_validator",
        passed=not issues,
        score=100.0 if not issues else max(0.0, 100.0 - 25 * len(issues)),
        issues=issues,
        details={"comparisons": comparisons, "threshold": limit, "signature_version": 2},
    )
