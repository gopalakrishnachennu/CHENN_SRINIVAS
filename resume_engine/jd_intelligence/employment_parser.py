"""Employment, engagement, and contract parsing."""

from __future__ import annotations

import re
from typing import Any

from resume_engine.jd_intelligence.schema import field, unknown
from resume_engine.jd_intelligence.text_utils import sentence_window


def parse_employment(text: str) -> dict[str, Any]:
    lower = (text or "").lower()
    employment = "UNKNOWN"
    engagement = "UNKNOWN"

    checks = [
        ("INTERNSHIP", r"\bintern(?:ship)?\b"),
        ("SEASONAL", r"\bseasonal\b"),
        ("TEMPORARY", r"\btemporary|temp\b"),
        ("PART_TIME", r"\bpart[- ]time\b"),
        ("CONTRACT", r"\bcontract\b"),
        ("FULL_TIME", r"\bfull[- ]time\b"),
    ]
    for value, pattern in checks:
        if re.search(pattern, lower):
            employment = value
            break

    engagement_checks = [
        ("C2H", r"\bcontract[- ]to[- ]hire|c2h\b"),
        ("C2C", r"\bc2c|corp[- ]to[- ]corp\b"),
        ("1099", r"\b1099\b"),
        ("W2", r"\bw-?2\b"),
        ("DIRECT_HIRE", r"\bdirect hire\b"),
    ]
    for value, pattern in engagement_checks:
        if re.search(pattern, lower):
            engagement = value
            break

    duration_value = duration_unit = None
    duration = re.search(r"\b(?P<value>\d+)\s*(?P<unit>month|months|week|weeks|year|years)\s+contract\b|\bcontract\s+(?:for\s+)?(?P<value2>\d+)\s*(?P<unit2>month|months|week|weeks|year|years)\b", lower)
    if duration:
        duration_value = int(duration.group("value") or duration.group("value2"))
        raw_unit = duration.group("unit") or duration.group("unit2")
        duration_unit = raw_unit.rstrip("s").upper()

    return {
        "employment_type": unknown(employment) if employment == "UNKNOWN" else field(employment, evidence=sentence_window(text, employment.replace("_", "[- ]"))),
        "engagement_type": unknown(engagement) if engagement == "UNKNOWN" else field(engagement, evidence=sentence_window(text, engagement)),
        "contract_duration_value": duration_value,
        "contract_duration_unit": duration_unit,
        "expected_start_date": None,
        "expected_end_date": None,
    }
