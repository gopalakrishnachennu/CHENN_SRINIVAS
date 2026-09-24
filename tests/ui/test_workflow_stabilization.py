"""UI regression tests for Phase 3.2 / 3.2.1 workflow stabilization."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from resume_engine.config.settings import get_ui_artifact_dir
from resume_engine.ui.db import connect_ui_db, ensure_ui_schema
from resume_engine.ui.services import candidate_service, job_service, match_service
from resume_engine.ui.services.blueprint_lifecycle import ANALYSIS_NEEDS, jd_content_hash
from resume_engine.ui.services.family_registry_service import reset_to_defaults
from tests.ui._helpers import csrf_from, make_client


@pytest.fixture(autouse=True)
def _restore_families():
    yield
    reset_to_defaults()


def _fake_analyze(jd_text: str, *, primary: str = "ai_ml", secondary: str | None = None, actor=None):
    ensure_ui_schema()
    jd_hash = jd_content_hash(jd_text)
    blueprint = {
        "jd_hash": jd_hash,
        "job": {
            "target_title": f"{primary} Role",
            "seniority": "mid",
            "primary_family": primary,
            "secondary_family": secondary or "none",
            "hybrid_probability": 0.1,
        },
        "priority_skills": {"P1": ["Python"], "P2": [], "P3": [], "P4": []},
        "responsibilities": ["Do work"],
        "certifications": [],
    }
    out_dir = get_ui_artifact_dir() / "test_blueprints"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"ui_{jd_hash}.json"
    path.write_text(json.dumps(blueprint), encoding="utf-8")
    return {"blueprint": blueprint, "path": str(path)}


def _mock_analyze(monkeypatch):
    def _analyze(jd_text, *, actor=None):
        text = (jd_text or "").lower()
        if "data engineer" in text:
            return _fake_analyze(jd_text, primary="data_engineering", actor=actor)
        if "salesforce" in text:
            return _fake_analyze(jd_text, primary="salesforce", actor=actor)
        return _fake_analyze(jd_text, primary="ai_ml", actor=actor)

    monkeypatch.setattr("resume_engine.ui.services.jd_service.analyze_jd", _analyze)


def _insert_pending(primary: str = "ai_ml", title: str = "Pending AI Role") -> str:
    from datetime import UTC, datetime

    now = datetime.now(UTC).isoformat()
    jid = str(uuid.uuid4())
    with connect_ui_db() as conn:
        conn.execute(
            """
            INSERT INTO jd_library(
              id, title, company, primary_family, status, jd_text,
              metadata_json, created_at, updated_at, analysis_status
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (jid, title, "Co", primary, "active", "AI engineer pending analysis text",
             "{}", now, now, ANALYSIS_NEEDS),
        )
        conn.commit()
    return jid


def test_create_page_never_shows_unmatched_job(monkeypatch):
    _mock_analyze(monkeypatch)
    client = make_client(monkeypatch)
    cand = candidate_service.create_profile({
        "candidate_name": "UI Cand A",
        "primary_family": "ai_ml",
        "companies": [{"company": "A", "start_date": "2020-01", "end_date": "2021-01"}],
    })
    ai = job_service.analyze_and_store("AI engineer pytorch")
    sf = job_service.analyze_and_store("Salesforce administrator apex")
    page = client.get(f"/create/?candidate={cand['id']}")
    html = page.data.decode()
    assert ai["id"] in html or ai["title"] in html
    assert sf["id"] not in html


def test_removed_secondary_family_updates_matches(monkeypatch):
    """HTTP: removing secondary clears DE matches immediately (strict, no COMPATIBLE)."""
    _mock_analyze(monkeypatch)
    client = make_client(monkeypatch)
    cand = candidate_service.create_profile({
        "candidate_name": "UI Cand B",
        "primary_family": "ai_ml",
        "secondary_family": "data_engineering",
        "companies": [{"company": "B", "start_date": "2020-01", "end_date": "2021-01"}],
    })
    de = job_service.analyze_and_store("Data Engineer spark kafka")
    ai = job_service.analyze_and_store("AI engineer pytorch unique")
    before = client.get(f"/matches/?candidate_id={cand['id']}")
    assert de["id"] in before.data.decode() or de["title"] in before.data.decode()

    # Edit via HTTP POST
    edit = client.get(f"/candidates/{cand['id']}/edit")
    token = csrf_from(edit.data.decode())
    client.post(
        f"/candidates/{cand['id']}/edit",
        data={
            "csrf_token": token,
            "candidate_name": "UI Cand B",
            "primary_family": "ai_ml",
            "secondary_family": "",
            "company_name": "B",
            "company_start": "2020-01",
            "company_end": "2021-01",
        },
        follow_redirects=True,
    )
    after = client.get(f"/matches/?candidate_id={cand['id']}")
    html = after.data.decode()
    assert de["id"] not in html
    assert ai["id"] in html or "resume-ready" in html.lower()


def test_missing_blueprint_job_is_not_selectable(monkeypatch):
    _mock_analyze(monkeypatch)
    client = make_client(monkeypatch)
    cand = candidate_service.create_profile({
        "candidate_name": "UI Cand C",
        "primary_family": "ai_ml",
        "companies": [{"company": "C", "start_date": "2020-01", "end_date": "2021-01"}],
    })
    job = job_service.analyze_and_store("AI engineer")
    Path(job["blueprint_path"]).unlink()
    with connect_ui_db() as conn:
        conn.execute(
            "UPDATE jd_library SET analysis_status = ?, blueprint_path = NULL WHERE id = ?",
            (ANALYSIS_NEEDS, job["id"]),
        )
        conn.commit()
    # Not a resume match on Create / Matches
    page = client.get(f"/create/?candidate={cand['id']}")
    assert job["id"] not in page.data.decode()
    matches = client.get(f"/matches/?candidate={cand['id']}")
    assert job["id"] not in matches.data.decode()
    # Still visible on Jobs library
    jobs_page = client.get("/jobs/")
    assert "NEEDS ANALYSIS" in jobs_page.data.decode() or job["title"] in jobs_page.data.decode()


def test_pending_job_shows_analyze_action(monkeypatch):
    _mock_analyze(monkeypatch)
    client = make_client(monkeypatch)
    _insert_pending()
    page = client.get("/jobs/")
    html = page.data.decode()
    assert "NEEDS ANALYSIS" in html or "Analyze Pending" in html


def test_generate_disabled_until_preflight_passes(monkeypatch):
    _mock_analyze(monkeypatch)
    client = make_client(monkeypatch)
    cand = candidate_service.create_profile({
        "candidate_name": "UI Cand E",
        "primary_family": "ai_ml",
        "companies": [{"company": "E", "start_date": "2020-01", "end_date": "2021-01"}],
    })
    _insert_pending(title="Pending Only Role")
    page = client.get(f"/create/?candidate={cand['id']}")
    html = page.data.decode()
    assert 'id="generate-btn"' in html
    assert "disabled" in html


def test_jd_change_invalidates_blueprint(monkeypatch):
    _mock_analyze(monkeypatch)
    job = job_service.analyze_and_store("AI engineer original")
    assert job["analysis_status"] == "READY"
    updated = job_service.update_job(job["id"], {"jd_text": "Salesforce brand new text"})
    assert updated["analysis_status"] == ANALYSIS_NEEDS


def test_candidate_family_change_invalidates_matches(monkeypatch):
    _mock_analyze(monkeypatch)
    cand = candidate_service.create_profile({
        "candidate_name": "UI Cand F",
        "primary_family": "ai_ml",
        "companies": [{"company": "F", "start_date": "2020-01", "end_date": "2021-01"}],
    })
    ai = job_service.analyze_and_store("AI engineer")
    matches = match_service.list_matches_for_candidate(cand)
    assert any(m["id"] == ai["id"] for m in matches)
    candidate_service.update_profile(cand["id"], {
        **cand["payload"],
        "primary_family": "salesforce",
    })
    refreshed = candidate_service.get_profile(cand["id"])
    matches2 = match_service.list_matches_for_candidate(refreshed)
    assert all(m["id"] != ai["id"] for m in matches2)


def test_archived_job_not_recommended(monkeypatch):
    _mock_analyze(monkeypatch)
    client = make_client(monkeypatch)
    cand = candidate_service.create_profile({
        "candidate_name": "UI Cand G",
        "primary_family": "ai_ml",
        "companies": [{"company": "G", "start_date": "2020-01", "end_date": "2021-01"}],
    })
    job = job_service.analyze_and_store("AI engineer archive me")
    job_service.archive_job(job["id"])
    page = client.get(f"/matches/?candidate_id={cand['id']}")
    assert job["id"] not in page.data.decode()
    create_page = client.get(f"/create/?candidate={cand['id']}")
    assert job["id"] not in create_page.data.decode()


def test_create_prepare_never_raw_blueprint_path_error(monkeypatch):
    _mock_analyze(monkeypatch)
    client = make_client(monkeypatch)
    cand = candidate_service.create_profile({
        "candidate_name": "UI Cand H",
        "primary_family": "ai_ml",
        "companies": [{"company": "H", "start_date": "2020-01", "end_date": "2021-01"}],
    })
    jid = _insert_pending(title="Prep Role")
    page = client.get(f"/create/?candidate={cand['id']}")
    token = csrf_from(page.data.decode())
    resp = client.post(
        "/create/prepare",
        data={
            "csrf_token": token,
            "candidate_id": cand["id"],
            "jd_id_prepare": jid,
        },
        follow_redirects=True,
    )
    html = resp.data.decode()
    assert "has no blueprint_path" not in html
    assert "Job ready" in html or "Preparing" in html or "READY" in html


def test_matches_paginated_not_thousand_cards(monkeypatch):
    _mock_analyze(monkeypatch)
    client = make_client(monkeypatch)
    cand = candidate_service.create_profile({
        "candidate_name": "UI Cand Page",
        "primary_family": "ai_ml",
        "companies": [{"company": "P", "start_date": "2020-01", "end_date": "2021-01"}],
    })
    for i in range(25):
        job_service.analyze_and_store(f"AI engineer pagination {i} unique text {uuid.uuid4()}")
    page = client.get(f"/matches/?candidate={cand['id']}")
    html = page.data.decode()
    assert "Page 1 / 2" in html
    assert html.count('class="match-row card"') == 20
    assert "Next" in html
    # Must not render all 25 job cards on page 1
    assert html.count('class="match-row card"') < 25


def test_compatible_not_in_normal_matches(monkeypatch):
    _mock_analyze(monkeypatch)
    client = make_client(monkeypatch)
    cand = candidate_service.create_profile({
        "candidate_name": "UI Cand Compat",
        "primary_family": "ai_ml",
        "companies": [{"company": "Z", "start_date": "2020-01", "end_date": "2021-01"}],
    })
    de = job_service.analyze_and_store("Data Engineer spark only no ai secondary")
    page = client.get(f"/matches/?candidate={cand['id']}")
    assert de["id"] not in page.data.decode()
