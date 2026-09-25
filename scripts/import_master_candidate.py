"""Import the verified local master profile into the UI candidate registry."""

from __future__ import annotations

import json
import re
from pathlib import Path

from resume_engine.config.settings import PROJECT_ROOT
from resume_engine.ui.services.candidate_service import create_profile, list_profiles


def master_to_candidate(master: dict) -> dict:
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
        "primary_family": "data_engineering",
        "secondary_family": "infrastructure_support",
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


def main() -> None:
    master = json.loads((PROJECT_ROOT / "candidate_profile.json").read_text(encoding="utf-8"))
    payload = master_to_candidate(master)
    existing = next(
        (item for item in list_profiles() if item["payload"].get("email") == payload["email"]),
        None,
    )
    if existing:
        print(f"Existing candidate: {existing['id']} {existing['name']}")
        return
    created = create_profile(payload, actor="master_profile_import")
    print(f"Imported candidate: {created['id']} {created['name']}")


if __name__ == "__main__":
    main()
