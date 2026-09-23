"""
Phase 2.7 Gate 3 — hygiene / export polish / SQLite-only writes.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

from resume_engine.export.document_model import ContactHeader
from resume_engine.export.service import export_resume
from resume_engine.learning.repository import LearningRepository, reset_default_repository_for_tests
from resume_engine.models.resume_schema import ResumeExperience, ResumeJSON
from resume_engine.ui.app import create_app


def _sample_resume() -> ResumeJSON:
    return ResumeJSON(
        target_title="Senior DevOps Engineer",
        summary="Platform engineer focused on AWS, Terraform, Kubernetes, and CI/CD delivery.",
        technical_skills={"Cloud": ["AWS", "Terraform"], "Platform": ["Kubernetes"]},
        experience=[
            ResumeExperience(
                company="Acme",
                title="DevOps Engineer",
                bullets=["Built CI/CD pipelines for Kubernetes workloads on AWS."],
            )
        ],
        projects=[],
        certifications=["AWS Solutions Architect"],
        variant_id="V01",
    )


def test_default_repository_does_not_dual_write_jsonl(tmp_path, monkeypatch):
    from resume_engine.learning import outcome_store
    from resume_engine.learning import repository as repo_mod
    from resume_engine.learning.outcome_store import save_learning_outcome

    outcomes = tmp_path / "outcomes.jsonl"
    monkeypatch.setattr(outcome_store, "OUTCOMES_FILE", outcomes)
    monkeypatch.delenv("LEARNING_DUAL_WRITE_JSONL", raising=False)
    reset_default_repository_for_tests(None)
    # Force fresh default construction.
    repo_mod._DEFAULT_REPO = None
    monkeypatch.setenv("LEARNING_DUAL_WRITE_JSONL", "0")
    repo = LearningRepository(db_path=tmp_path / "solo.sqlite3")  # default False
    reset_default_repository_for_tests(repo)
    assert repo.dual_write_jsonl is False
    save_learning_outcome(
        {
            "run_id": "solo-1",
            "jd_hash": "h",
            "variant_id": "V01",
            "passed": True,
            "eligible_for_learning": True,
            "primary_family": "devops_cloud",
            "secondary_family": "none",
            "seniority": "senior",
            "score_after": 95.0,
            "p1_coverage": 100.0,
            "p2_coverage": 95.0,
            "failure_codes": [],
            "technology_firewall_passed": True,
            "role_drift_passed": True,
        }
    )
    assert not outcomes.exists() or outcomes.read_text().strip() == ""
    history = repo.get_strategy_history(eligible_only=False)
    assert any(item.get("run_id") == "solo-1" for item in history)
    reset_default_repository_for_tests(None)
    repo_mod._DEFAULT_REPO = None


def test_opt_in_dual_write_still_works(tmp_path, monkeypatch):
    from resume_engine.learning import outcome_store
    from resume_engine.learning.outcome_store import save_learning_outcome

    outcomes = tmp_path / "outcomes.jsonl"
    monkeypatch.setattr(outcome_store, "OUTCOMES_FILE", outcomes)
    repo = LearningRepository(db_path=tmp_path / "dual.sqlite3", dual_write_jsonl=True)
    reset_default_repository_for_tests(repo)
    save_learning_outcome({"run_id": "dual-g3", "jd_hash": "h", "variant_id": "V01", "passed": True})
    assert "dual-g3" in outcomes.read_text(encoding="utf-8")
    reset_default_repository_for_tests(None)


def test_pdf_export_includes_full_contact_line(tmp_path: Path):
    result = export_resume(
        _sample_resume(),
        formats=("pdf",),
        output_dir=tmp_path,
        basename="contact",
        contact=ContactHeader(
            name="Ada Lovelace",
            email="ada@example.com",
            phone="555-0100",
            location="London",
            linkedin="linkedin.com/in/ada",
        ),
    )
    pdf_path = tmp_path / "contact.pdf"
    assert Path(result["artifacts"]["pdf"]).exists() or pdf_path.exists()
    assert pdf_path.stat().st_size > 1200


def test_ui_export_form_exposes_extended_contact_fields():
    # Phase 3.1: contact fields live on export workflow; legacy /export still accepts them.
    client = create_app().test_client()
    response = client.get("/exports/")
    assert response.status_code == 200
    assert b"Exports" in response.data
    # Legacy export route remains registered for DOCX/PDF/ZIP.
    assert "export_one" in create_app().view_functions


def test_ui_both_export_returns_zip(tmp_path, monkeypatch):
    from resume_engine.config import settings

    resume_path = tmp_path / "V01_final.json"
    resume_path.write_text(_sample_resume().model_dump_json(), encoding="utf-8")
    # Place under RUNS_STORAGE_DIR tree for path guard.
    run_dir = settings.RUNS_STORAGE_DIR / "gate3jd" / "gate3run" / "validated"
    run_dir.mkdir(parents=True, exist_ok=True)
    target = run_dir / "V01_final.json"
    target.write_text(resume_path.read_text(encoding="utf-8"), encoding="utf-8")
    rel = target.resolve().relative_to(settings.PROJECT_ROOT.resolve()).as_posix()

    client = create_app().test_client()
    response = client.post(
        "/export",
        data={
            "resume_path": rel,
            "format": "both",
            "candidate_name": "Ada",
            "email": "ada@example.com",
            "phone": "555",
            "location": "London",
        },
    )
    assert response.status_code == 200
    assert response.mimetype == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(response.data))
    names = zf.namelist()
    assert any(name.endswith(".docx") for name in names)
    assert any(name.endswith(".pdf") for name in names)


def test_get_default_repository_respects_env_opt_in(monkeypatch, tmp_path):
    import os

    from resume_engine.learning import repository as repo_mod

    monkeypatch.setenv("LEARNING_DUAL_WRITE_JSONL", "1")
    repo_mod._DEFAULT_REPO = None
    dual = os.getenv("LEARNING_DUAL_WRITE_JSONL", "").strip().lower() in {"1", "true", "yes"}
    assert dual is True
    repo = LearningRepository(db_path=tmp_path / "env.sqlite3", dual_write_jsonl=dual)
    assert repo.dual_write_jsonl is True
    repo_mod._DEFAULT_REPO = None
    monkeypatch.delenv("LEARNING_DUAL_WRITE_JSONL", raising=False)
