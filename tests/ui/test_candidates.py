from resume_engine.ui.services import candidate_service
from tests.ui._helpers import csrf_from, make_client


def test_candidate_profile_crud(monkeypatch, tmp_path):
    # isolate db? uses shared sqlite — ok for unit create/archive
    client = make_client(monkeypatch)
    page = client.get("/candidates/new")
    token = csrf_from(page.data.decode())
    r = client.post("/candidates/new", data={
        "csrf_token": token,
        "candidate_name": "Test Candidate UI",
        "email": "t@example.com",
        "technical_skills": "Python, SQL",
        "experience_json": "[]",
        "projects_json": "[]",
        "education_json": "[]",
    }, follow_redirects=True)
    assert r.status_code == 200
    profiles = candidate_service.list_profiles()
    assert any(p["name"] == "Test Candidate UI" for p in profiles)
    target = next(p for p in profiles if p["name"] == "Test Candidate UI")
    versions = candidate_service.list_versions(target["id"])
    assert len(versions) >= 1
