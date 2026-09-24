from resume_engine.ui.services import candidate_service
from tests.ui._helpers import csrf_from, make_client


def test_candidate_profile_crud(monkeypatch, tmp_path):
    client = make_client(monkeypatch)
    page = client.get("/candidates/new")
    assert page.status_code == 200
    assert b"Primary Job Family" in page.data
    assert b"technical_skills" not in page.data
    assert b"Job Title" not in page.data
    token = csrf_from(page.data.decode())
    r = client.post(
        "/candidates/new",
        data={
            "csrf_token": token,
            "candidate_name": "Test Candidate UI",
            "email": "t@example.com",
            "primary_family": "ai_ml",
            "secondary_family": "data_engineering",
            "company_name": "Acme",
            "company_start": "Jan 2020",
            "company_end": "Present",
            "certifications": "AWS SAA",
            "education": "BS Computer Science",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    profiles = candidate_service.list_profiles()
    assert any(p["name"] == "Test Candidate UI" for p in profiles)
    target = next(p for p in profiles if p["name"] == "Test Candidate UI")
    assert target["payload"]["primary_family"] == "ai_ml"
    assert target["payload"]["companies"][0]["company"] == "Acme"
    assert "technical_skills" not in target["payload"] or target["payload"].get("technical_skills") in (None, [])
    versions = candidate_service.list_versions(target["id"])
    assert len(versions) >= 1
