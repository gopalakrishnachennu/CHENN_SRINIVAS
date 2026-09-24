from __future__ import annotations

from tests.ui._helpers import csrf_from, make_client

JD = """
Senior Machine Learning Engineer
Austin, TX
Hybrid, three days in office
Full-time W2
Salary: $150,000-$190,000 annually.
Must be authorized to work in the United States.
We cannot provide sponsorship now or in the future.
8+ years software engineering.
Bachelor's degree in Computer Science or equivalent experience.
Python, PyTorch, AWS.
Up to 10% travel.
"""

MICROSOFT_JD = """
Microsoft lists a Principal Software Engineer - FullStack role in Noida for
high-scale Office web platforms. Responsibilities include architecture and
design, performance benchmarking, reliable and maintainable code, feature
development, tests, modernization proofs of concept and identifying AI
opportunities that improve engineering productivity. Preferred experience
includes large-scale cloud/web engineering, performance and scalability,
modern software practices and interest in AI or machine learning.
"""


def _save_draft(client):
    page = client.get("/jobs/new")
    token = csrf_from(page.data.decode())
    resp = client.post(
        "/jobs/new",
        data={
            "csrf_token": token,
            "action": "draft",
            "title": "Senior Machine Learning Engineer",
            "company": "Acme",
            "location": "Austin, TX",
            "source": "manual",
            "job_url": "https://example.test/jobs/123",
            "jd_text": JD,
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    return resp.headers["Location"]


def test_save_draft_does_not_require_model_analysis(monkeypatch):
    client = make_client(monkeypatch)
    location = _save_draft(client)
    detail = client.get(location)
    html = detail.data.decode()
    assert detail.status_code == 200
    assert "Location & Work" in html
    assert "Job Description" in html
    assert "Laya Workflow Review" in html
    assert "Senior Machine Learning Engineer" in html
    assert "Austin" in html
    assert "HYBRID" in html
    assert "NO_SPONSORSHIP" in html
    assert "AUTHORIZED_TO_WORK_US" in html


def test_job_filters_use_phase33_columns(monkeypatch):
    client = make_client(monkeypatch)
    _save_draft(client)
    filtered = client.get(
        "/jobs/?work_mode=HYBRID&employment_type=FULL_TIME&salary_status=STATED"
        "&authorization_requirement=AUTHORIZED_TO_WORK_US&student_visa_status=OPT_CPT_NOT_STATED"
        "&clearance_status=NOT_STATED&min_experience=8&max_experience=9"
    )
    html = filtered.data.decode()
    assert filtered.status_code == 200
    assert "Senior Machine Learning Engineer" in html
    assert "HYBRID" in html
    assert "150,000" in html
    assert "AUTHORIZED_TO_WORK_US" in html
    assert "OPT_CPT_NOT_STATED" in html


def test_edit_and_raw_jd_pages(monkeypatch):
    client = make_client(monkeypatch)
    location = _save_draft(client)
    job_id = location.rstrip("/").split("/")[-1]
    edit = client.get(f"/jobs/{job_id}/edit")
    raw = client.get(f"/jobs/{job_id}/raw")
    assert edit.status_code == 200
    assert raw.status_code == 200
    assert "Raw JD" in raw.data.decode()
    assert "Manual JD Text" in raw.data.decode()
    assert "JD URL" in edit.data.decode()
    assert "Application Metrics" in edit.data.decode()


def test_manual_override_updates_detail_history_and_filters(monkeypatch):
    client = make_client(monkeypatch)
    location = _save_draft(client)
    job_id = location.rstrip("/").split("/")[-1]
    detail = client.get(f"/jobs/{job_id}?advanced=1")
    token = csrf_from(detail.data.decode())

    resp = client.post(
        f"/jobs/{job_id}/override",
        data={
            "csrf_token": token,
            "field_name": "work_mode",
            "new_value": "REMOTE",
            "reason": "Recruiter confirmed remote role.",
        },
        follow_redirects=True,
    )
    html = resp.data.decode()
    assert resp.status_code == 200
    assert "Manual Override History" in html
    assert "work_mode" in html
    assert "REMOTE" in html
    assert "Recruiter confirmed remote role." in html
    assert "manual override: work_mode" in html

    filtered = client.get("/jobs/?work_mode=REMOTE")
    filtered_html = filtered.data.decode()
    assert filtered.status_code == 200
    assert "Senior Machine Learning Engineer" in filtered_html
    assert "REMOTE" in filtered_html


def test_analysis_versions_are_visible_in_advanced_job_review(monkeypatch):
    client = make_client(monkeypatch)
    location = _save_draft(client)
    job_id = location.rstrip("/").split("/")[-1]
    detail = client.get(f"/jobs/{job_id}?advanced=1")
    html = detail.data.decode()
    assert detail.status_code == 200
    assert "Analysis Versions" in html
    assert "analysis" in html
    assert "job-intelligence-v1" in html


def test_edit_save_auto_assigns_family_seniority_and_application_metrics(monkeypatch):
    client = make_client(monkeypatch)
    page = client.get("/jobs/new")
    token = csrf_from(page.data.decode())
    created = client.post(
        "/jobs/new",
        data={
            "csrf_token": token,
            "action": "draft",
            "title": "Principal Software Engineer - FullStack",
            "company": "Microsoft",
            "location": "Noida, Uttar Pradesh",
            "source": "manual",
            "job_url": "https://careers.microsoft.com/jobs/J010",
            "jd_text": MICROSOFT_JD,
        },
        follow_redirects=False,
    )
    job_id = created.headers["Location"].rstrip("/").split("/")[-1]
    edit = client.get(f"/jobs/{job_id}/edit")
    edit_html = edit.data.decode()
    assert "Laya Role Assignment" in edit_html
    assert "Software Engineering" in edit_html
    assert "AI / ML" in edit_html
    assert "principal" in edit_html
    assert "https://careers.microsoft.com/jobs/J010" in edit_html
    assert "Country" not in edit_html or "United States" not in edit_html

    token = csrf_from(edit_html)
    saved = client.post(
        f"/jobs/{job_id}/edit",
        data={
            "csrf_token": token,
            "title": "Principal Software Engineer - FullStack",
            "company": "Microsoft",
            "location": "Noida, Uttar Pradesh",
            "job_url": "https://careers.microsoft.com/jobs/J010",
            "jd_text": MICROSOFT_JD + "\nSalary: INR 45L-60L annually.",
        },
        follow_redirects=True,
    )
    html = saved.data.decode()
    assert "Software Engineering" in html
    assert "AI / ML" in html
    assert "principal" in html
    assert "https://careers.microsoft.com/jobs/J010" in html
    assert "INR" in html
    assert "City: <strong>Noida</strong>" in html
    assert "State: <strong>Uttar Pradesh</strong>" in html
    assert "Country: <strong>India</strong>" in html


def test_job_intake_blocks_missing_required_fields(monkeypatch):
    client = make_client(monkeypatch)
    page = client.get("/jobs/new")
    token = csrf_from(page.data.decode())
    resp = client.post(
        "/jobs/new",
        data={
            "csrf_token": token,
            "action": "draft",
            "title": "AI Engineer",
            "company": "",
            "location": "",
            "source": "manual",
            "job_url": "",
            "jd_text": "AI engineer",
        },
        follow_redirects=True,
    )
    html = resp.data.decode()
    assert resp.status_code == 200
    assert "Required job intake fields missing" in html
    assert "Company" in html
    assert "Location" in html
    assert "JD URL" in html


def test_incomplete_job_detail_shows_laya_blocker(monkeypatch):
    client = make_client(monkeypatch)
    page = client.get("/jobs/new")
    token = csrf_from(page.data.decode())
    created = client.post(
        "/jobs/new",
        data={
            "csrf_token": token,
            "action": "draft",
            "title": "AI Engineer",
            "company": "Acme",
            "location": "Austin, TX",
            "source": "manual",
            "job_url": "https://example.test/jobs/ai",
            "jd_text": "AI engineer\nLocation: Austin, TX",
        },
        follow_redirects=False,
    )
    job_id = created.headers["Location"].rstrip("/").split("/")[-1]

    from resume_engine.ui.db import connect_ui_db

    with connect_ui_db() as conn:
        conn.execute("UPDATE jd_library SET company = '' WHERE id = ?", (job_id,))
        conn.commit()

    detail = client.get(f"/jobs/{job_id}")
    html = detail.data.decode()
    assert "Required Intake Missing" in html
    assert "Laya Workflow Review" in html
    assert "BLOCKED" in html


def test_edit_blocks_missing_required_intake_and_preserves_existing_job(monkeypatch):
    client = make_client(monkeypatch)
    location = _save_draft(client)
    job_id = location.rstrip("/").split("/")[-1]
    edit = client.get(f"/jobs/{job_id}/edit")
    token = csrf_from(edit.data.decode())
    resp = client.post(
        f"/jobs/{job_id}/edit",
        data={
            "csrf_token": token,
            "title": "Senior Machine Learning Engineer",
            "company": "Acme",
            "location": "",
            "job_url": "https://example.test/jobs/123",
            "jd_text": JD,
        },
        follow_redirects=True,
    )
    html = resp.data.decode()
    assert resp.status_code == 200
    assert "Required job intake fields missing" in html
    assert "Location" in html

    detail = client.get(location)
    assert "Austin" in detail.data.decode()
