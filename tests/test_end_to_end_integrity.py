"""End-to-end workflow integrity — Phase 3.2 stabilization."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from resume_engine.ui.db import connect_ui_db, ensure_ui_schema
from resume_engine.ui.services import candidate_service, job_service, match_service
from resume_engine.ui.services.blueprint_lifecycle import (
    ANALYSIS_NEEDS,
    ANALYSIS_READY,
    ensure_job_blueprint,
    get_analysis_status,
    jd_content_hash,
)
from resume_engine.ui.services.create_resume_service import (
    PreflightError,
    preflight_create_resume,
)
from resume_engine.ui.services.family_registry_service import reset_to_defaults
from resume_engine.ui.services.match_service import (
    MATCH_NONE,
    MATCH_SECONDARY,
    match_candidate_to_job,
)


@pytest.fixture(autouse=True)
def _restore_families():
    yield
    reset_to_defaults()


def _fake_analyze(jd_text: str, *, primary: str = "ai_ml", secondary: str | None = None, actor=None):
    """Deterministic Phase-1 stand-in for tests (no OpenAI)."""
    ensure_ui_schema()
    jd_hash = jd_content_hash(jd_text)
    blueprint = {
        "jd_hash": jd_hash,
        "job": {
            "target_title": "Test Role",
            "seniority": "mid",
            "primary_family": primary,
            "secondary_family": secondary or "none",
            "hybrid_probability": 0.1,
        },
        "priority_skills": {"P1": ["Python"], "P2": ["SQL"], "P3": [], "P4": []},
        "responsibilities": ["Build things"],
        "certifications": [],
    }
    from resume_engine.config.settings import get_ui_artifact_dir

    out_dir = get_ui_artifact_dir() / "test_blueprints"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{jd_hash}.json"
    path.write_text(json.dumps(blueprint, indent=2), encoding="utf-8")
    return {"blueprint": blueprint, "path": str(path)}


def _insert_imported_job(
    *,
    title: str,
    primary: str | None,
    jd_text: str,
    job_id: str | None = None,
    analysis_status: str = ANALYSIS_NEEDS,
    blueprint_path: str | None = None,
) -> str:
    ensure_ui_schema()
    from datetime import UTC, datetime

    now = datetime.now(UTC).isoformat()
    jid = job_id or str(uuid.uuid4())
    with connect_ui_db() as conn:
        conn.execute(
            """
            INSERT INTO jd_library(
              id, jd_hash, title, company, location, job_url, source,
              seniority, primary_family, secondary_family, status,
              blueprint_path, jd_text, metadata_json, created_at, updated_at,
              analysis_status, analysis_version, jd_content_hash
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                jid, None, title, "Co", "Remote, United States", "https://example.test/imported", "import",
                "mid", primary, None, "active",
                blueprint_path, jd_text, "{}", now, now,
                analysis_status, 0, None,
            ),
        )
        conn.commit()
    return jid


def _analyzed_job(text: str):
    return job_service.analyze_and_store(
        text,
        company="Acme",
        location="Austin, TX",
        job_url=f"https://example.test/jobs/{uuid.uuid4()}",
    )


@pytest.fixture
def mock_analyze(monkeypatch):
    def _analyze(jd_text, *, actor=None):
        text = (jd_text or "").lower()
        if "data engineer" in text or "spark" in text:
            return _fake_analyze(jd_text, primary="data_engineering", actor=actor)
        if "salesforce" in text:
            return _fake_analyze(jd_text, primary="salesforce", actor=actor)
        return _fake_analyze(jd_text, primary="ai_ml", actor=actor)

    monkeypatch.setattr(
        "resume_engine.ui.services.jd_service.analyze_jd",
        _analyze,
    )
    return _analyze


def test_end_to_end_happy_path_then_secondary_removal(mock_analyze):
    cand = candidate_service.create_profile({
        "candidate_name": "E2E Cand",
        "primary_family": "ai_ml",
        "secondary_family": "data_engineering",
        "companies": [{"company": "Acme", "start_date": "2020-01", "end_date": "2023-01"}],
    })
    assert cand["payload"]["secondary_family"] == "data_engineering"

    ai_job = _analyzed_job("Senior ML Engineer Python PyTorch")
    de_job = _analyzed_job("Data Engineer Spark Airflow pipelines")
    assert get_analysis_status(ai_job) == ANALYSIS_READY
    assert ai_job["blueprint_path"] and Path(ai_job["blueprint_path"]).exists()

    matches = match_service.list_matches_for_candidate(cand)
    ids = {m["id"] for m in matches}
    assert ai_job["id"] in ids
    assert de_job["id"] in ids

    check = preflight_create_resume(cand["id"], ai_job["id"])
    assert check["ok"] is True

    # Remove secondary — DE must disappear under STRICT matching (no COMPATIBLE fallback)
    updated = candidate_service.update_profile(cand["id"], {
        **cand["payload"],
        "secondary_family": None,
    })
    assert updated["payload"]["secondary_family"] is None
    assert updated["version"] >= 2

    refreshed = candidate_service.get_profile(cand["id"])
    matches2 = match_service.list_matches_for_candidate(refreshed)
    ids2 = {m["id"] for m in matches2}
    assert ai_job["id"] in ids2
    assert de_job["id"] not in ids2
    de_result = match_candidate_to_job(refreshed, de_job)
    assert de_result.match_type == MATCH_NONE


def test_ensure_job_blueprint_regenerates_missing_file(mock_analyze, tmp_path):
    job = _analyzed_job("AI engineer LLM RAG")
    path = Path(job["blueprint_path"])
    assert path.exists()
    path.unlink()
    result = ensure_job_blueprint(job["id"])
    assert result["ok"] is True
    assert Path(result["blueprint_path"]).exists()
    refreshed = job_service.get_job(job["id"])
    assert get_analysis_status(refreshed) == ANALYSIS_READY


def test_jd_text_edit_invalidates_blueprint(mock_analyze):
    job = _analyzed_job("ML engineer tensorflow keras")
    old_path = job["blueprint_path"]
    old_hash = job["jd_content_hash"]
    updated = job_service.update_job(job["id"], {"jd_text": "Completely new Salesforce Admin Apex LWC JD text here"})
    assert updated["analysis_status"] == ANALYSIS_NEEDS
    assert not updated.get("blueprint_path")
    assert updated.get("jd_content_hash") in (None, "")
    result = ensure_job_blueprint(job["id"])
    assert result["ok"] is True
    refreshed = job_service.get_job(job["id"])
    assert refreshed["analysis_status"] == ANALYSIS_READY
    assert refreshed["blueprint_path"] != old_path or refreshed["jd_content_hash"] != old_hash
    assert refreshed["primary_family"] == "salesforce"


def test_no_match_cannot_generate(mock_analyze):
    cand = candidate_service.create_profile({
        "candidate_name": "SF Only",
        "primary_family": "salesforce",
        "companies": [{"company": "Org", "start_date": "2019-01", "end_date": "Present"}],
    })
    ai_job = _analyzed_job("Machine learning engineer deep learning")
    with pytest.raises(PreflightError) as exc:
        preflight_create_resume(cand["id"], ai_job["id"])
    assert exc.value.code == "FAMILY_NO_LONGER_MATCHES"


def test_ready_cannot_exist_with_missing_blueprint(mock_analyze):
    job = _analyzed_job("AI research engineer")
    Path(job["blueprint_path"]).unlink()
    with connect_ui_db() as conn:
        conn.execute(
            "UPDATE jd_library SET analysis_status = 'READY', blueprint_path = ? WHERE id = ?",
            ("/tmp/does_not_exist_blueprint.json", job["id"]),
        )
        conn.commit()
    effective = get_analysis_status(job_service.get_job(job["id"]))
    assert effective != ANALYSIS_READY

    from resume_engine.maintenance.reconcile import check_integrity, repair_integrity

    report = check_integrity()
    assert any(
        i["code"] == "READY_MISSING_BLUEPRINT" and i.get("job_id") == job["id"]
        for i in report["issues"]
    )
    repair_integrity()
    after = job_service.get_job(job["id"])
    assert after["analysis_status"] == ANALYSIS_NEEDS


def test_imported_job_not_auto_ready():
    jid = _insert_imported_job(
        title="Imported Role",
        primary="ai_ml",
        jd_text="Imported JD without blueprint",
    )
    job = job_service.get_job(jid)
    assert job["analysis_status"] == ANALYSIS_NEEDS
    cand = candidate_service.create_profile({
        "candidate_name": "Import Cand",
        "primary_family": "ai_ml",
        "companies": [{"company": "X", "start_date": "2021-01", "end_date": "2022-01"}],
    })
    with pytest.raises(PreflightError) as exc:
        preflight_create_resume(cand["id"], jid)
    assert exc.value.code == "JOB_BLUEPRINT_NOT_READY"


def test_secondary_only_match_then_removed():
    """Regression: secondary removal clears SECONDARY match (COMPATIBLE ignored)."""
    cand = {
        "payload": {"primary_family": "ai_ml", "secondary_family": "data_engineering"},
    }
    de_job = {"primary_family": "data_engineering", "secondary_family": None}
    before = match_candidate_to_job(cand, de_job)
    assert before.match_type == MATCH_SECONDARY

    cand2 = {"payload": {"primary_family": "ai_ml", "secondary_family": None}}
    after = match_candidate_to_job(cand2, de_job)
    assert after.match_type == MATCH_NONE


def test_archived_job_cannot_generate(mock_analyze):
    cand = candidate_service.create_profile({
        "candidate_name": "Arch Cand",
        "primary_family": "ai_ml",
        "companies": [{"company": "Y", "start_date": "2020-01", "end_date": "2021-01"}],
    })
    job = _analyzed_job("AI engineer")
    job_service.archive_job(job["id"])
    with pytest.raises(PreflightError) as exc:
        preflight_create_resume(cand["id"], job["id"])
    assert exc.value.code == "JOB_ARCHIVED"


def test_candidate_zero_companies_preflight_fails(mock_analyze):
    cand = candidate_service.create_profile({
        "candidate_name": "No Co",
        "primary_family": "ai_ml",
        "companies": [],
    })
    job = _analyzed_job("AI engineer")
    with pytest.raises(PreflightError) as exc:
        preflight_create_resume(cand["id"], job["id"])
    assert exc.value.code == "CANDIDATE_COMPANY_HISTORY_MISSING"


def test_primary_equals_secondary_normalized():
    data = candidate_service.normalize_payload({
        "candidate_name": "Dup",
        "primary_family": "ai_ml",
        "secondary_family": "ai_ml",
    })
    assert data["secondary_family"] is None


def test_secondary_sentinels_become_none():
    for raw in ("", "None", "null", "none", None):
        data = candidate_service.normalize_payload({
            "candidate_name": "S",
            "primary_family": "ai_ml",
            "secondary_family": raw,
        })
        assert data["secondary_family"] is None
