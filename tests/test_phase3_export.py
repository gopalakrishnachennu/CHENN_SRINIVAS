"""
Phase 3 export + UI tests (DOCX/PDF only; no ATS parser / job application engine).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from resume_engine.export.document_model import ContactHeader, build_document_view
from resume_engine.export.service import export_resume
from resume_engine.models.resume_schema import ResumeExperience, ResumeJSON, ResumeProject
from resume_engine.ui.app import create_app, list_validated_resumes

pytestmark = pytest.mark.unit


def _sample_resume() -> ResumeJSON:
    return ResumeJSON(
        target_title="Senior DevOps Engineer",
        summary="Platform engineer focused on AWS, Terraform, Kubernetes, and CI/CD delivery.",
        technical_skills={
            "Cloud": ["AWS", "Terraform"],
            "Platform": ["Kubernetes", "CI/CD", "Python"],
        },
        experience=[
            ResumeExperience(
                company="Acme",
                title="DevOps Engineer",
                bullets=[
                    "Built CI/CD pipelines for Kubernetes workloads on AWS.",
                    "Automated infrastructure with Terraform and Python.",
                ],
            )
        ],
        projects=[
            ResumeProject(
                name="Platform Automation",
                summary="Delivery automation for containerized services.",
                bullets=["Reduced release friction with reusable pipelines."],
                technologies=["AWS", "Kubernetes", "Terraform"],
            )
        ],
        certifications=["AWS Solutions Architect"],
        variant_id="V01",
        source_blueprint_hash="demo_jd_hash",
    )


def test_build_document_view_includes_sections():
    view = build_document_view(
        _sample_resume(),
        contact={"candidate_name": "Ada Lovelace", "email": "ada@example.com"},
    )
    assert view.title == "Senior DevOps Engineer"
    assert view.contact.name == "Ada Lovelace"
    assert "ada@example.com" in view.contact.contact_line()
    assert view.experience[0]["company"] == "Acme"
    assert "AWS" in view.technical_skills["Cloud"]


def test_export_docx_and_pdf(tmp_path: Path):
    result = export_resume(
        _sample_resume(),
        formats=("docx", "pdf"),
        output_dir=tmp_path,
        basename="V01_final",
        contact=ContactHeader(name="Ada Lovelace", email="ada@example.com"),
    )
    assert result["artifacts"]["docx"]
    assert result["artifacts"]["pdf"]
    docx_path = tmp_path / "V01_final.docx"
    pdf_path = tmp_path / "V01_final.pdf"
    assert docx_path.exists() and docx_path.stat().st_size > 1000
    assert pdf_path.exists() and pdf_path.stat().st_size > 1000


def test_export_rejects_unknown_format(tmp_path: Path):
    with pytest.raises(ValueError, match="Unsupported export format"):
        export_resume(_sample_resume(), formats=("xlsx",), output_dir=tmp_path)


def test_docx_contains_key_phrases(tmp_path: Path):
    from docx import Document

    export_resume(
        _sample_resume(),
        formats=("docx",),
        output_dir=tmp_path,
        basename="check",
        contact={"candidate_name": "Ada Lovelace"},
    )
    doc = Document(str(tmp_path / "check.docx"))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "Ada Lovelace" in text
    assert "Professional Summary" in text.upper() or "PROFESSIONAL SUMMARY" in text.upper()
    assert "Kubernetes" in text
    assert "Acme" in text


def test_ui_index_loads():
    client = create_app().test_client()
    response = client.get("/")
    assert response.status_code == 200
    assert b"Control Center" in response.data or b"Dashboard" in response.data


def test_list_validated_resumes_returns_list():
    items = list_validated_resumes(limit=5)
    assert isinstance(items, list)


def test_phase3_cli_export(tmp_path: Path):
    resume_path = tmp_path / "resume.json"
    resume_path.write_text(_sample_resume().model_dump_json(), encoding="utf-8")
    out_dir = tmp_path / "out"

    from phase_3_export import main

    code = main(
        [
            "export",
            "--resume",
            str(resume_path),
            "--format",
            "docx,pdf",
            "--out-dir",
            str(out_dir),
            "--basename",
            "cli_resume",
        ]
    )
    assert code == 0
    assert (out_dir / "cli_resume.docx").exists()
    assert (out_dir / "cli_resume.pdf").exists()
