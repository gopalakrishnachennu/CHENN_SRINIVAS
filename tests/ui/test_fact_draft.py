from resume_engine.generation.fact_draft import build_fact_draft
from resume_engine.ui.services.candidate_service import normalize_payload, to_engine_candidate_profile
from scripts.import_master_candidate import master_to_candidate


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
    profile = to_engine_candidate_profile(normalize_payload(master_to_candidate(master)))
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
