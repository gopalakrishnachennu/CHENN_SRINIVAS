"""Tests for the Phase 3.2 product UI redesign."""

from tests.ui._helpers import make_client


def test_primary_nav_pages_200(monkeypatch):
    client = make_client(monkeypatch)
    for path in [
        "/", "/candidates/", "/jobs/", "/matches/",
        "/resumes/", "/create/",
    ]:
        resp = client.get(path)
        assert resp.status_code == 200, f"{path} returned {resp.status_code}"


def test_advanced_pages_200(monkeypatch):
    client = make_client(monkeypatch)
    for path in [
        "/advanced/families/", "/advanced/laya/",
        "/blueprints/", "/strategies/", "/validation/",
        "/repairs/", "/learning/", "/registry/",
        "/prompts/", "/settings/", "/audit/", "/system/",
    ]:
        resp = client.get(path)
        assert resp.status_code == 200, f"{path} returned {resp.status_code}"


def test_legacy_routes_accessible(monkeypatch):
    client = make_client(monkeypatch)
    for path in ["/generate/", "/jd/", "/runs/"]:
        resp = client.get(path)
        assert resp.status_code == 200, f"{path} returned {resp.status_code}"


def test_family_registry_list(monkeypatch):
    from resume_engine.ui.services import family_registry_service
    families = family_registry_service.list_families()
    assert len(families) >= 10
    ids = [f["family_id"] for f in families]
    assert "ai_ml" in ids
    assert "data_engineering" in ids
    assert "software_engineering" in ids


def test_family_registry_resolve(monkeypatch):
    from resume_engine.ui.services.family_registry_service import resolve_family
    assert resolve_family("ai_ml") == "ai_ml"
    assert resolve_family("AI / ML") == "ai_ml"
    assert resolve_family("ML") == "ai_ml"
    assert resolve_family("nonexistent") is None


def test_deterministic_matching():
    from resume_engine.ui.services.match_service import compute_match_type

    direct = compute_match_type("ai_ml", None, "ai_ml", None)
    assert direct["match_type"] == "DIRECT"
    assert direct["score"] == 1.0

    # Strict: no set overlap → NO_MATCH (COMPATIBLE disabled by default)
    no_overlap = compute_match_type("data_engineering", None, "ai_ml", None)
    assert no_overlap["match_type"] == "NO_MATCH"

    # Adjacent / compatible only when opted in
    adjacent = compute_match_type(
        "data_engineering", None, "ai_ml", None, include_compatible=True
    )
    assert adjacent["match_type"] == "COMPATIBLE"

    secondary = compute_match_type(
        "software_engineering", "data_analytics", "data_analytics", None,
    )
    assert secondary["match_type"] == "SECONDARY"

    hybrid = compute_match_type(
        "ai_ml", None, "data_engineering", "ai_ml",
    )
    assert hybrid["match_type"] == "HYBRID"

    no_match = compute_match_type(
        "salesforce", None, "ai_ml", None,
    )
    assert no_match["match_type"] == "NO_MATCH"


def test_candidate_product_model(monkeypatch):
    client = make_client(monkeypatch)
    page = client.get("/candidates/new")
    assert page.status_code == 200
    html = page.data.decode()
    assert "Primary Job Family" in html or "primary_family" in html
    assert "Company" in html


def test_jobs_analyze_page(monkeypatch):
    client = make_client(monkeypatch)
    for path in ["/jobs/new", "/jobs/analyze"]:
        resp = client.get(path)
        assert resp.status_code == 200


def test_nav_structure(monkeypatch):
    client = make_client(monkeypatch)
    resp = client.get("/")
    html = resp.data.decode()
    assert "Create Resume" in html
    assert "Candidates" in html
    assert "Jobs" in html
    assert "Matches" in html
    assert "Resumes" in html
    assert "Advanced" in html
    assert "JD Workspace" not in html or "nav-link" not in html.split("JD Workspace")[0][-50:]


def test_river_active_locked(monkeypatch):
    from resume_engine.ui.services.learning_service import (
        try_enable_active_mode,
    )
    try:
        try_enable_active_mode()
        raise AssertionError("Active mode should be locked")
    except PermissionError:
        pass


def test_candidate_provenance_fields(monkeypatch):
    from resume_engine.ui.services.candidate_service import (
        normalize_payload,
    )
    data = normalize_payload({
        "candidate_name": "Test",
        "primary_family": "ai_ml",
        "companies": [
            {"company": "Acme", "start_date": "2020", "end_date": "2023"},
        ],
    })
    assert data["_schema"] == "candidate_facts_v2"
    assert data["companies"][0]["provenance"]["company"] == "VERIFIED_CANDIDATE_INPUT"
    assert data["companies"][0]["provenance"]["role_title"] == "NOT_PROVIDED"
