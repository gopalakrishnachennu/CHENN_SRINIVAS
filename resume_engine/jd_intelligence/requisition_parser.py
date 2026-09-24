"""Job identity parser for requisition and external job IDs."""

from __future__ import annotations

import re
from typing import Any

from resume_engine.jd_intelligence.schema import field, not_stated
from resume_engine.jd_intelligence.text_utils import compact


def parse_requisition(text: str) -> dict[str, Any]:
    match = re.search(r"\b(?:requisition|req|job)\s*(?:id|#|number|no\.?)\s*[:#-]?\s*([A-Za-z0-9_-]{3,40})\b", text or "", re.IGNORECASE)
    if not match:
        return {
            "requisition_id": not_stated("NOT_STATED"),
            "external_job_id": not_stated("NOT_STATED"),
        }
    value = match.group(1)
    evidence = compact(match.group(0))
    return {
        "requisition_id": field(value, evidence=evidence),
        "external_job_id": field(value, evidence=evidence),
    }
