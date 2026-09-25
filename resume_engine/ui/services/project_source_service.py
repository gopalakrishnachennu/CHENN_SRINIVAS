"""Review and import the project's fixed, local candidate and JD sources."""

from __future__ import annotations

import json
import re
from typing import Any

from resume_engine.config.settings import PROJECT_ROOT
from resume_engine.ui.services import candidate_service, family_registry_service


def candidate_source() -> dict[str, Any] | None:
    path = PROJECT_ROOT / "candidate_profile.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Project candidate profile must be a JSON object.")
    return data


def jd_source() -> dict[str, str] | None:
    path = PROJECT_ROOT / "real_jd.txt"
    if not path.is_file():
        return None
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return None
    lines = raw.splitlines()
    title = next((line.strip() for line in lines if line.strip()), "")
    location = next(
        (line.split(":", 1)[1].strip() for line in lines if line.strip().lower().startswith("location:") and ":" in line),
        "",
    )
    return {"title": title, "location": location, "jd_text": raw, "source": "project file: real_jd.txt"}


def existing_candidate(master: dict[str, Any]) -> dict[str, Any] | None:
    email = str(master.get("email") or "").strip().casefold()
    if not email:
        return None
    return next(
        (profile for profile in candidate_service.list_profiles(include_archived=True)
         if str(profile["payload"].get("email") or "").strip().casefold() == email),
        None,
    )


def master_to_candidate(
    master: dict[str, Any], *, primary_family: str, secondary_family: str | None = None
) -> dict[str, Any]:
    companies = []
    for item in master.get("experience") or []:
        dates = re.split(r"\s+[–—-]\s+", str(item.get("dates") or ""), maxsplit=1)
        companies.append({
            "company": item.get("company") or "",
            "title": item.get("title") or "",
            "start_date": dates[0] if dates else "",
            "end_date": dates[1] if len(dates) > 1 else "",
            "responsibilities": item.get("truthful_facts") or [],
        })
    return {
        "candidate_name": master.get("candidate_name") or "",
        "email": master.get("email") or "",
        "phone": master.get("phone") or "",
        "location": master.get("location") or "",
        "linkedin": master.get("linkedin") or "",
        "website": master.get("website") or "",
        "primary_family": primary_family,
        "secondary_family": secondary_family,
        "companies": companies,
        "verified_skills": master.get("technical_skills") or [],
        "verified_summary": master.get("target_background_summary") or "",
        "verified_projects": [
            {"name": item.get("name") or "", "facts": item.get("truthful_facts") or []}
            for item in master.get("projects") or []
        ],
        "education": master.get("education") or [],
        "certifications": master.get("certifications") or [],
    }


def import_candidate(
    *, primary_family: str, secondary_family: str | None = None, actor: str | None = None
) -> dict[str, Any]:
    master = candidate_source()
    if master is None:
        raise ValueError("candidate_profile.json is not available in this project.")
    existing = existing_candidate(master)
    if existing:
        raise ValueError("This candidate is already imported. Open the existing profile to review it.")
    primary = family_registry_service.resolve_family(primary_family)
    secondary = family_registry_service.resolve_family(secondary_family)
    if not primary or (secondary_family and not secondary):
        raise ValueError("Select valid job families before importing.")
    payload = master_to_candidate(master, primary_family=primary, secondary_family=secondary)
    if not payload["candidate_name"] or not payload["companies"]:
        raise ValueError("The project profile needs a name and company history.")
    return candidate_service.create_profile(payload, actor=actor)


def refresh_candidate(*, actor: str | None = None) -> dict[str, Any]:
    master = candidate_source()
    if master is None:
        raise ValueError("candidate_profile.json is not available in this project.")
    existing = existing_candidate(master)
    if existing is None:
        raise ValueError("Import the project candidate before refreshing it.")
    current = existing["payload"]
    payload = master_to_candidate(
        master,
        primary_family=current.get("primary_family") or "",
        secondary_family=current.get("secondary_family"),
    )
    if not payload["candidate_name"] or not payload["companies"]:
        raise ValueError("The project profile needs a name and company history.")
    return candidate_service.update_profile(existing["id"], payload, actor=actor)
