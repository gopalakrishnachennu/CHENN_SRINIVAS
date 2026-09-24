"""Strict family matching rules (COMPATIBLE off by default)."""

from __future__ import annotations

from resume_engine.ui.services import candidate_service, job_service
from resume_engine.ui.services.match_service import (
    MATCH_DIRECT,
    MATCH_HYBRID,
    MATCH_NONE,
    MATCH_SECONDARY,
    load_family_registry_snapshot,
    match_candidate_to_job,
    match_summary_for_candidate,
)


def test_strict_direct():
    r = match_candidate_to_job(
        {"payload": {"primary_family": "ai_ml"}},
        {"primary_family": "ai_ml"},
    )
    assert r.match_type == MATCH_DIRECT


def test_strict_secondary():
    r = match_candidate_to_job(
        {"payload": {"primary_family": "ai_ml", "secondary_family": "data_engineering"}},
        {"primary_family": "data_engineering"},
    )
    assert r.match_type == MATCH_SECONDARY


def test_strict_hybrid_overlap():
    r = match_candidate_to_job(
        {"payload": {"primary_family": "ai_ml", "secondary_family": None}},
        {"primary_family": "data_engineering", "secondary_family": "ai_ml"},
    )
    assert r.match_type == MATCH_HYBRID


def test_strict_no_match_without_overlap():
    r = match_candidate_to_job(
        {"payload": {"primary_family": "ai_ml", "secondary_family": None}},
        {"primary_family": "data_engineering", "secondary_family": None},
    )
    assert r.match_type == MATCH_NONE


def test_compatible_opt_in_only():
    cand = {"payload": {"primary_family": "ai_ml"}}
    job = {"primary_family": "data_engineering"}
    assert match_candidate_to_job(cand, job).match_type == MATCH_NONE
    from resume_engine.ui.services.match_service import MATCH_COMPATIBLE

    assert (
        match_candidate_to_job(cand, job, include_compatible=True).match_type
        == MATCH_COMPATIBLE
    )


def test_registry_loaded_once_for_batch(monkeypatch):
    calls = {"n": 0}
    real = load_family_registry_snapshot

    def counted():
        calls["n"] += 1
        return real()

    monkeypatch.setattr(
        "resume_engine.ui.services.match_service.load_family_registry_snapshot",
        counted,
    )
    # match_summary loads snapshot once
    cand = candidate_service.create_profile({
        "candidate_name": "Strict Batch",
        "primary_family": "ai_ml",
        "companies": [{"company": "C", "start_date": "2020-01", "end_date": "2021-01"}],
    })
    jobs = []
    for i in range(30):
        jobs.append({
            "id": f"j{i}",
            "title": f"Role {i}",
            "company": "Co",
            "primary_family": "ai_ml" if i % 2 == 0 else "salesforce",
            "secondary_family": None,
            "status": "active",
            "analysis_status": "READY",
            "blueprint_path": __file__,  # exists
            "analysis_version": 1,
        })
    summary = match_summary_for_candidate(cand, jobs)
    assert summary["matched_jobs"] == 15
    assert calls["n"] == 1


def test_dedupe_analyze_and_store(monkeypatch):
    import json

    from resume_engine.config.settings import get_ui_artifact_dir
    from resume_engine.ui.services.blueprint_lifecycle import jd_content_hash

    def _analyze(jd_text, *, actor=None):
        h = jd_content_hash(jd_text)
        bp = {
            "jd_hash": h,
            "job": {
                "target_title": "Dedupe Role",
                "seniority": "mid",
                "primary_family": "ai_ml",
                "secondary_family": "none",
            },
            "priority_skills": {"P1": ["Python"], "P2": [], "P3": [], "P4": []},
        }
        path = get_ui_artifact_dir() / "test_blueprints" / f"{h}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(bp), encoding="utf-8")
        return {"blueprint": bp, "path": str(path)}

    monkeypatch.setattr("resume_engine.ui.services.jd_service.analyze_jd", _analyze)
    text = "Unique JD body for dedupe test abc123"
    a = job_service.analyze_and_store(text, company="Acme")
    b = job_service.analyze_and_store(text, company="Acme")
    assert a["id"] == b["id"]
