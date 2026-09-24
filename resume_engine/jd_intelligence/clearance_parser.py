"""Security clearance parser."""

from __future__ import annotations

import re
from typing import Any

from resume_engine.jd_intelligence.schema import field, not_stated
from resume_engine.jd_intelligence.text_utils import sentence_window


def parse_clearance(text: str) -> dict[str, Any]:
    evidence = sentence_window(text, r"\b(clearance|public trust|secret|top secret|TS/SCI|TS SCI)\b")
    if not evidence:
        return {
            "clearance_status": not_stated("NOT_STATED"),
            "clearance_level": not_stated("NOT_STATED"),
            "clearance_evidence": None,
        }
    lower = evidence.lower()
    status = "PREFERRED" if "preferred" in lower else "REQUIRED"
    if "not required" in lower or "no clearance" in lower:
        status = "NOT_REQUIRED"
    if re.search(r"ts/sci|ts sci", lower):
        level = "TS_SCI"
    elif "top secret" in lower:
        level = "TOP_SECRET"
    elif "secret" in lower:
        level = "SECRET"
    elif "public trust" in lower:
        level = "PUBLIC_TRUST"
    elif "confidential" in lower:
        level = "CONFIDENTIAL"
    else:
        level = "OTHER"
    return {
        "clearance_status": field(status, evidence=evidence),
        "clearance_level": field(level, evidence=evidence),
        "clearance_evidence": evidence,
    }
