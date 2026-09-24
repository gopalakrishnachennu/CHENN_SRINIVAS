"""Education parser."""

from __future__ import annotations

import re
from typing import Any

from resume_engine.jd_intelligence.schema import field
from resume_engine.jd_intelligence.text_utils import sentence_window

DEGREES = [
    ("BACHELOR", r"\bbachelor'?s?\b|\bBS\b|\bBA\b"),
    ("MASTER", r"\bmaster'?s?\b|\bMS\b|\bMA\b"),
    ("PHD", r"\bPh\.?D\b|doctorate"),
    ("ASSOCIATE", r"\bassociate'?s?\b"),
]


def parse_education(text: str) -> dict[str, Any]:
    required: list[str] = []
    preferred: list[str] = []
    majors_required: list[str] = []
    majors_preferred: list[str] = []
    evidence = None
    for level, pattern in DEGREES:
        hit = sentence_window(text, pattern)
        if not hit:
            continue
        evidence = hit
        if "preferred" in hit.lower():
            preferred.append(level)
        else:
            required.append(level)
        major = re.search(r"\bin\s+([A-Z][A-Za-z ]{2,50}?)(?:\s+or|,|\.|$)", hit)
        if major:
            target = majors_preferred if "preferred" in hit.lower() else majors_required
            target.append(major.group(1).strip())
    equivalent = None
    if re.search(r"\bequivalent experience\b", text or "", re.IGNORECASE):
        equivalent = True
    return {
        "education_required": field(bool(required), status="EXPLICIT" if required else "NOT_STATED", evidence=evidence),
        "required_degree_levels": required,
        "preferred_degree_levels": preferred,
        "required_majors": majors_required,
        "preferred_majors": majors_preferred,
        "equivalent_experience_accepted": equivalent,
    }
