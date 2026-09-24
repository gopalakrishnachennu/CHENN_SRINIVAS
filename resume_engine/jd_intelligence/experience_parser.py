"""Experience requirements parser."""

from __future__ import annotations

import re
from typing import Any

from resume_engine.jd_intelligence.schema import field, not_stated
from resume_engine.jd_intelligence.text_utils import compact


def parse_experience(text: str) -> dict[str, Any]:
    matches = list(re.finditer(r"\b(?P<min>\d+)\s*(?:\+|plus)?\s*(?:-|to)?\s*(?P<max>\d+)?\s*\+?\s*years?\s+(?:of\s+)?(?P<area>[A-Za-z /+-]{2,80})", text or "", re.IGNORECASE))
    required: list[str] = []
    preferred: list[str] = []
    minimum = preferred_years = None
    for match in matches:
        area = compact(match.group("area")).rstrip(".")
        evidence = compact(match.group(0))
        target = preferred if "preferred" in evidence.lower() else required
        target.append(area)
        years = int(match.group("min"))
        if target is preferred:
            preferred_years = years if preferred_years is None else min(preferred_years, years)
        else:
            minimum = years if minimum is None else min(minimum, years)
    return {
        "minimum_years_experience": field(minimum, evidence=[compact(m.group(0)) for m in matches]) if minimum is not None else not_stated(None),
        "preferred_years_experience": preferred_years,
        "required_experience": required,
        "preferred_experience": preferred,
        "leadership_experience": [],
        "management_experience": [],
        "domain_experience": [],
        "industry_experience": [],
    }
