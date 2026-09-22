"""
Phase 2.7 Gate 2 — semantic correctness + learning SoT tests.
"""
from __future__ import annotations

import json
import uuid

from resume_engine.config import thresholds
from resume_engine.learning.fingerprint_signatures import (
    compute_minhash,
    compute_simhash64,
    minhash_jaccard,
    signature_near_duplicate,
    simhash_hamming,
)
from resume_engine.learning.fingerprint_store import (
    build_fingerprint_record,
    save_fingerprint,
    validate_cross_run_uniqueness,
)
from resume_engine.learning.strategy_memory import load_outcome_records
from resume_engine.models.resume_schema import ResumeJSON
from resume_engine.reports.behavioral_audit import _good_resume, _monster_blueprint
from resume_engine.storage.run_store import (
    create_run_paths,
    resolve_validated_final,
    save_validated_resume_artifact,
)
from resume_engine.validation.laya_validator import build_laya_responsibility_payload
from resume_engine.validation.responsibility_validator import validate_responsibilities


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


# ---------------------------------------------------------------------------
# Fingerprints / SimHash / MinHash
# ---------------------------------------------------------------------------


def test_simhash_identical_text_zero_hamming():
    text = "managed databricks terraform kubernetes kubernetes python ci/cd"
    a = compute_simhash64(text)
    b = compute_simhash64(text)
    assert a == b
    assert simhash_hamming(a, b) == 0


def test_minhash_identical_text_jaccard_one():
    text = "owned kubernetes spark workloads on aws with terraform"
    assert minhash_jaccard(compute_minhash(text), compute_minhash(text)) == 1.0


def test_near_duplicate_paraphrase_detected_by_signature():
    left = (
        "Managed Databricks platform operations on AWS using Terraform and Kubernetes. "
        "Automated CI/CD deployments with Python across cloud infrastructure paths. "
        "Built Apache Spark workloads for production data engineering needs."
    )
    right = (
        "Managed Databricks platform operations on AWS using Terraform and Kubernetes. "
        "Automated CI/CD deployments with Python across cloud infrastructure paths. "
        "Built Apache Spark workloads for production data engineering requirements."
    )
    near, diag = signature_near_duplicate(
        current_simhash=compute_simhash64(left),
        prior_simhash=compute_simhash64(right),
        current_minhash=compute_minhash(left),
        prior_minhash=compute_minhash(right),
    )
    assert near is True
    assert diag["simhash_hamming"] is not None or diag["minhash_jaccard"] is not None


def test_different_content_not_near_duplicate():
    left = "nursing patient care medication administration hospital ward"
    right = "databricks terraform kubernetes spark openai api cloud platform"
    near, _ = signature_near_duplicate(
        current_simhash=compute_simhash64(left),
        prior_simhash=compute_simhash64(right),
        current_minhash=compute_minhash(left),
        prior_minhash=compute_minhash(right),
    )
    assert near is False


def test_cross_run_signature_flags_near_duplicate(tmp_path, monkeypatch):
    from resume_engine.learning import fingerprint_store, repository as repo_mod
    from resume_engine.learning.repository import LearningRepository, reset_default_repository_for_tests

    fp_file = tmp_path / "fps.jsonl"
    monkeypatch.setattr(fingerprint_store, "FINGERPRINTS_FILE", fp_file)
    reset_default_repository_for_tests(
        LearningRepository(db_path=tmp_path / "fp.sqlite3", dual_write_jsonl=True)
    )
    monkeypatch.setattr(repo_mod, "FINGERPRINTS_FILE", fp_file, raising=False)

    bp = _monster_blueprint()
    resume = _good_resume("V01")
    save_fingerprint(
        jd_hash=bp.jd_hash,
        run_id="prior-run",
        variant_id="V01",
        resume=resume,
        passed=True,
    )
    # Near-identical regen with tiny wording change.
    near = resume.model_copy(deep=True)
    near.summary = resume.summary.replace("focused on", "centered on")
    result = validate_cross_run_uniqueness(near, bp.jd_hash, run_id="new-run")
    assert not result.passed
    assert any(i.code == "FAIL_CROSS_RUN_DUPLICATION" for i in result.issues)
    reset_default_repository_for_tests(None)


def test_fingerprint_record_includes_signatures():
    record = build_fingerprint_record(
        jd_hash="h",
        run_id="r",
        variant_id="V01",
        resume=_good_resume("V01"),
        passed=True,
    )
    assert "simhash64" in record
    assert isinstance(record["minhash"], list)
    assert len(record["minhash"]) == thresholds.FINGERPRINT_MINHASH_PERMUTATIONS
    assert record["signature_version"] == 2


# ---------------------------------------------------------------------------
# Laya responsibility budget
# ---------------------------------------------------------------------------


def test_laya_responsibilities_not_hard_capped_at_eight():
    bp = _monster_blueprint().model_copy(deep=True)
    bp.responsibilities = [f"Responsibility number {i} for cloud platforms" for i in range(1, 16)]
    payload = build_laya_responsibility_payload(bp)
    assert payload["responsibilities_total"] == 15
    assert payload["responsibilities_in_state"] == 15
    assert payload["responsibilities_truncated"] is False
    assert len(payload["responsibilities"]) == 15


def test_laya_prefer_uncovered_ids_first():
    bp = _monster_blueprint().model_copy(deep=True)
    bp.responsibilities = [f"Duty alpha {i} terraform kubernetes" for i in range(1, 12)]
    # Force a small budget.
    payload = build_laya_responsibility_payload(
        bp,
        uncovered_ids=["R010", "R011"],
        max_items=3,
    )
    ids = [e["id"] for e in payload["responsibility_entries"]]
    assert ids[0] == "R010"
    assert ids[1] == "R011"
    assert payload["responsibilities_truncated"] is True


# ---------------------------------------------------------------------------
# Responsibility uncovered IDs
# ---------------------------------------------------------------------------


def test_responsibility_exposes_uncovered_ids():
    bp = _monster_blueprint()
    resume = ResumeJSON(
        target_title="Engineer",
        summary="Generic engineer.",
        technical_skills={"Core": ["AWS"]},
        experience=[{"company": "A", "title": "E", "bullets": ["Did general work."]}],
        projects=[],
        certifications=[],
        variant_id="V01",
    )
    result = validate_responsibilities(bp, resume)
    assert "uncovered_responsibility_ids" in result.details
    assert isinstance(result.details["uncovered_responsibility_ids"], list)


def test_responsibility_bigram_boost_helps_phrase_match():
    bp = _monster_blueprint().model_copy(deep=True)
    bp.responsibilities = ["Automate CI/CD deployments using Terraform modules"]
    resume = ResumeJSON(
        target_title="Engineer",
        summary="Platform engineer.",
        technical_skills={"Core": ["Terraform", "CI/CD"]},
        experience=[
            {
                "company": "A",
                "title": "E",
                "bullets": ["Automate CI/CD deployments using Terraform modules for releases."],
            }
        ],
        projects=[],
        certifications=[],
        variant_id="V01",
    )
    result = validate_responsibilities(bp, resume)
    assert result.details["covered"] >= 1
    assert result.details["responsibility_mapping"]["R001"]["status"] == "PASS"


# ---------------------------------------------------------------------------
# SQLite learning SoT
# ---------------------------------------------------------------------------


def test_load_outcome_records_prefers_sqlite(tmp_path, monkeypatch):
    from resume_engine.learning import outcome_store, strategy_memory
    from resume_engine.learning.repository import LearningRepository, reset_default_repository_for_tests

    db = tmp_path / "sot.sqlite3"
    jsonl = tmp_path / "outcomes.jsonl"
    repo = LearningRepository(db_path=db, dual_write_jsonl=False)
    reset_default_repository_for_tests(repo)
    monkeypatch.setattr(outcome_store, "OUTCOMES_FILE", jsonl)
    monkeypatch.setattr(strategy_memory, "OUTCOMES_FILE", jsonl)

    repo.save_outcome(
        {
            "run_id": "r1",
            "jd_hash": "h",
            "variant_id": "V01",
            "variant_positioning": "platform_reliability",
            "primary_family": "devops_cloud",
            "secondary_family": "none",
            "hybrid": False,
            "seniority": "senior",
            "passed": True,
            "eligible_for_learning": True,
            "successful_pattern": True,
            "score_after": 96.0,
            "p1_coverage": 100.0,
            "p2_coverage": 95.0,
            "failure_codes": [],
            "technology_firewall_passed": True,
            "role_drift_passed": True,
        }
    )
    # JSONL intentionally empty — SoT must still return SQLite rows.
    assert not jsonl.exists() or jsonl.read_text().strip() == ""
    records = load_outcome_records()
    assert len(records) >= 1
    assert records[0]["variant_id"] == "V01"
    reset_default_repository_for_tests(None)


def test_explicit_outcomes_path_still_reads_jsonl(tmp_path):
    path = tmp_path / "custom.jsonl"
    path.write_text(json.dumps({"variant_id": "VX", "passed": True}) + "\n", encoding="utf-8")
    records = load_outcome_records(path)
    assert len(records) == 1
    assert records[0]["variant_id"] == "VX"


# ---------------------------------------------------------------------------
# Final pointer sync
# ---------------------------------------------------------------------------


def test_stable_final_syncs_to_selected_attempt():
    bp = _monster_blueprint()
    paths = create_run_paths(bp.jd_hash, run_id=_uid("ptr-sync"))
    a1 = _good_resume("V01")
    a1.summary = "FIRST"
    save_validated_resume_artifact(paths, "V01", a1, attempt_no=1)
    a2 = _good_resume("V01")
    a2.summary = "SECOND"
    save_validated_resume_artifact(paths, "V01", a2, attempt_no=2)
    stable = paths.validated_dir / "V01_final.json"
    assert "SECOND" in stable.read_text(encoding="utf-8")
    resolved = resolve_validated_final(paths, "V01")
    assert resolved is not None
    assert "SECOND" in resolved.read_text(encoding="utf-8")
    # Attempt history preserved.
    assert "FIRST" in (paths.validated_dir / "V01_attempt_01_final.json").read_text(encoding="utf-8")
