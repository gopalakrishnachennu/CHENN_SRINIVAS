"""Build an honest, exportable resume draft from verified candidate facts only."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any, Callable

from resume_engine.config.settings import portable_path
from resume_engine.export.service import export_resume
from resume_engine.models.jd_blueprint import JDBlueprint
from resume_engine.models.resume_schema import ResumeExperience, ResumeJSON, ResumeProject
from resume_engine.storage.run_store import create_run_paths, save_resume_artifact, write_run_metadata


def build_fact_draft(candidate: dict[str, Any], target_title: str, jd_hash: str) -> tuple[ResumeJSON, list[str]]:
    history = candidate.get("experience") or []
    if not candidate.get("candidate_name") or not history:
        raise ValueError("Candidate name and company history are required for a fact-only draft.")

    gaps: list[str] = []
    experience = []
    for item in history:
        company = str(item.get("company") or "").strip()
        if not company:
            continue
        title = str(item.get("title") or "").strip()
        bullets = [str(line).strip() for line in item.get("responsibilities") or [] if str(line).strip()]
        if not title:
            gaps.append(f"Role title at {company}")
        if not bullets:
            gaps.append(f"Work examples at {company}")
        experience.append(
            ResumeExperience(
                company=company,
                title=title,
                start_date=str(item.get("start_date") or ""),
                end_date=str(item.get("end_date") or ""),
                bullets=bullets,
            )
        )
    if not experience:
        raise ValueError("At least one named company is required for a fact-only draft.")

    skills = [str(skill).strip() for skill in candidate.get("technical_skills") or [] if str(skill).strip()]
    if not skills:
        gaps.append("Verified skills")
    if not candidate.get("email") and not candidate.get("phone"):
        gaps.append("Email or phone")

    projects = [
        ResumeProject(
            name=project["name"],
            summary="",
            bullets=project.get("facts") or [],
        )
        for project in candidate.get("projects") or []
        if project.get("name")
    ]
    education = []
    for item in candidate.get("education") or []:
        if isinstance(item, dict):
            line = " - ".join(str(item.get(key) or "").strip() for key in ("degree", "school") if item.get(key))
            line = line or str(item.get("description") or "").strip()
        else:
            line = str(item).strip()
        if line:
            education.append(line)
    verified_summary = str(candidate.get("target_background_summary") or "").strip()
    summary = verified_summary or f"Verified employment history for consideration for {target_title}."
    resume = ResumeJSON(
        target_title=target_title,
        summary=summary,
        technical_skills={"Verified skills": skills} if skills else {},
        experience=experience,
        projects=projects,
        certifications=[str(cert).strip() for cert in candidate.get("certifications") or [] if str(cert).strip()],
        education=education,
        variant_id="V01",
        source_blueprint_hash=jd_hash,
    )
    return resume, gaps


def create_fact_draft(
    *,
    blueprint_path: str | Path | None = None,
    target_title: str | None = None,
    jd_hash: str | None = None,
    jd_text: str | None = None,
    candidate_profile_path: str | Path,
    run_id: str,
    formats: list[str],
    progress_callback: Callable[[str, str, dict[str, Any] | None], None] | None = None,
) -> dict[str, Any]:
    blueprint = JDBlueprint.from_json_file(str(blueprint_path)) if blueprint_path else None
    title = blueprint.job.target_title if blueprint else str(target_title or "Professional Background").strip()
    hash_value = blueprint.jd_hash if blueprint else jd_hash or hashlib.sha256(title.encode("utf-8")).hexdigest()[:32]
    candidate = json.loads(Path(candidate_profile_path).read_text(encoding="utf-8"))
    if progress_callback:
        progress_callback("draft", "Assembling verified candidate facts; no OpenAI request.", None)
    resume, gaps = build_fact_draft(candidate, title, hash_value)
    paths = create_run_paths(hash_value, run_id=run_id)
    write_run_metadata(paths, {"generation_mode": "FACT_DRAFT", "openai_requests": 0})
    if jd_text:
        (paths.root / "source_jd.txt").write_text(jd_text, encoding="utf-8")
    source_path = save_resume_artifact(paths.raw_dir, "V01_fact_draft.json", resume)
    exports = []
    if formats:
        if progress_callback:
            progress_callback("export", "Exporting fact-only draft.", {"formats": formats})
        exported = export_resume(
            resume,
            formats=formats,
            output_dir=paths.root / "exports",
            basename="fact_only_draft",
            contact=candidate,
        )
        exports.append({"variant_id": "V01", "artifacts": exported["artifacts"]})
    result = {
        "phase": "Fact-only draft",
        "run_id": paths.run_id,
        "jd_hash": hash_value,
        "generation_mode": "FACT_DRAFT",
        "draft": True,
        "candidate_profile": portable_path(candidate_profile_path),
        "blueprint": portable_path(blueprint_path) if blueprint_path else None,
        "target_title": title,
        "source_jd": portable_path(paths.root / "source_jd.txt") if jd_text else None,
        "scope": "Verified candidate facts with the JD title as the target; no requirement-level tailoring.",
        "run_root": portable_path(paths.root),
        "variants_processed": 1,
        "variant_results": [{
            "variant_id": "V01", "status": "FACT_DRAFT", "passed": False,
            "raw_resume": portable_path(source_path), "evidence_gaps": gaps,
        }],
        "evidence_gaps": gaps,
        "exports": exports,
    }
    summary = paths.root / "phase2_summary.json"
    summary.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    result["summary_path"] = portable_path(summary)
    return result
