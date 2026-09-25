import json

from resume_engine.generation.fact_draft import build_fact_draft
from resume_engine.ui.services.candidate_service import normalize_payload, to_engine_candidate_profile
from resume_engine.ui.services.project_source_service import master_to_candidate
from tests.ui._helpers import csrf_from, make_client


def test_project_sources_ui_import_and_draft_without_active_job(monkeypatch, tmp_path):
    from resume_engine.ui.db import connect_ui_db
    from resume_engine.ui.services import create_resume_service, generation_service, project_source_service

    (tmp_path / "candidate_profile.json").write_text(json.dumps({
        "candidate_name": "Verified Person", "email": "verified@example.com",
        "experience": [{"company": "Example Corp", "title": "DBA",
                        "dates": "Jan 2020 - Present", "truthful_facts": ["Maintained backups."]}],
    }), encoding="utf-8")
    (tmp_path / "real_jd.txt").write_text(
        "Database Administrator II\nLocation: Plano, TX\nMaintain SQL Server.", encoding="utf-8"
    )
    monkeypatch.setattr(project_source_service, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(create_resume_service, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(generation_service, "start_generation_job", lambda _id: None)
    client = make_client(monkeypatch)
    page = client.get("/create/project-sources")
    html = page.data.decode()
    assert page.status_code == 200
    assert "Verified Person" in html
    assert "Database Administrator II" in html
    token = csrf_from(html)
    imported = client.post("/create/project-sources", data={
        "csrf_token": token, "action": "import_candidate", "primary_family": "data_engineering",
    })
    assert imported.status_code == 302
    candidate_id = imported.headers["Location"].rsplit("/", 1)[-1]
    assert "Already imported" in client.get("/create/project-sources").data.decode()
    version_before = None
    with connect_ui_db() as conn:
        version_before = conn.execute(
            "SELECT MAX(version) FROM candidate_profile_versions WHERE profile_id = ?", (candidate_id,)
        ).fetchone()[0]
    denied_refresh = client.post("/create/project-sources", data={
        "csrf_token": token, "action": "refresh_candidate",
    })
    assert denied_refresh.status_code == 200
    with connect_ui_db() as conn:
        assert conn.execute(
            "SELECT MAX(version) FROM candidate_profile_versions WHERE profile_id = ?", (candidate_id,)
        ).fetchone()[0] == version_before
    refreshed = client.post("/create/project-sources", data={
        "csrf_token": token, "action": "refresh_candidate", "confirm_refresh": "on",
    })
    assert refreshed.status_code == 302
    with connect_ui_db() as conn:
        assert conn.execute(
            "SELECT MAX(version) FROM candidate_profile_versions WHERE profile_id = ?", (candidate_id,)
        ).fetchone()[0] == version_before + 1
    job_form = client.get("/jobs/new?from_project_jd=1").data.decode()
    assert "Maintain SQL Server." in job_form
    assert 'name="company" value=""' in job_form
    with client.session_transaction() as session:
        token = session["_csrf_token"]
    started = client.post("/create/project-sources", data={
        "csrf_token": token, "action": "create_draft", "candidate_id": candidate_id,
    })
    assert started.status_code == 302
    with connect_ui_db() as conn:
        job_count = conn.execute("SELECT COUNT(*) FROM jd_library").fetchone()[0]
        draft = conn.execute("SELECT status, job_id FROM resume_library").fetchone()
    assert job_count == 0
    assert draft["status"] == "generating"
    assert draft["job_id"].startswith("project-jd:")
    (tmp_path / "candidate_profile.json").write_text("{invalid", encoding="utf-8")
    assert "Candidate source could not be read" in client.get("/create/project-sources").data.decode()


def test_local_draft_is_registered_before_worker_starts(monkeypatch, tmp_path):
    from resume_engine.ui.db import connect_ui_db
    from resume_engine.ui.services import candidate_service, create_resume_service, generation_service, job_service, match_service

    monkeypatch.setattr(create_resume_service, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(candidate_service, "get_profile", lambda _id: {
        "payload": {
            "candidate_name": "Verified Person",
            "primary_family": "data_engineering",
            "companies": [{"company": "Example Corp", "start_date": "2020", "end_date": "2022"}],
        },
    })
    monkeypatch.setattr(job_service, "get_job", lambda _id: {
        "title": "Database Administrator II", "jd_hash": "testhash",
    })
    monkeypatch.setattr(match_service, "match_candidate_to_job", lambda *_args: type("Match", (), {"match_type": "DIRECT"})())
    observed = []

    def worker_start(job_id):
        with connect_ui_db() as conn:
            rows = conn.execute("SELECT run_id FROM resume_library").fetchall()
        observed.append((job_id, len(rows)))

    monkeypatch.setattr(generation_service, "start_generation_job", worker_start)
    job = create_resume_service.start_resume_creation(
        candidate_id="candidate-1", job_id="job-1", match_type="FACT_DRAFT",
        local_draft=True, export_docx=True, export_pdf=True,
    )
    assert observed == [(job["job_id"], 1)]
    progress = create_resume_service.friendly_progress(job)
    assert progress["call_policy"] == "0 OpenAI calls"
    assert progress["model"] == "Local facts"
    assert progress["openai_key"]["label"] == "Not used"


def test_master_profile_preserves_verified_evidence():
    master = {
        "candidate_name": "Verified Person",
        "technical_skills": ["SQL Server"],
        "experience": [{
            "company": "Example Corp",
            "title": "Database Administrator",
            "dates": "Jan 2020 - Present",
            "truthful_facts": ["Maintained SQL Server backups."],
        }],
        "projects": [{"name": "Restore testing", "truthful_facts": ["Tested restores."]}],
    }
    profile = to_engine_candidate_profile(normalize_payload(master_to_candidate(master, primary_family="data_engineering")))
    resume, gaps = build_fact_draft(profile, "Database Administrator II", "testhash")
    assert gaps == ["Email or phone"]
    assert resume.experience[0].title == "Database Administrator"
    assert resume.experience[0].start_date == "Jan 2020"
    assert resume.experience[0].end_date == "Present"
    assert resume.experience[0].bullets == ["Maintained SQL Server backups."]
    assert resume.projects[0].bullets == ["Tested restores."]
    assert resume.technical_skills == {"Verified skills": ["SQL Server"]}


def test_sparse_profile_does_not_invent_role_or_work_examples():
    resume, gaps = build_fact_draft({
        "candidate_name": "Verified Person",
        "experience": [{"company": "Example Corp", "start_date": "2021", "end_date": "2022"}],
    }, "Database Administrator II", "testhash")
    assert resume.experience[0].title == ""
    assert resume.experience[0].bullets == []
    assert "Role title at Example Corp" in gaps
    assert "Work examples at Example Corp" in gaps
    assert "Verified skills" in gaps
