"""Work mode, relocation, travel, shift, and schedule parsing."""

from __future__ import annotations

import re
from typing import Any

from resume_engine.jd_intelligence.schema import field, unknown
from resume_engine.jd_intelligence.text_utils import (
    compact,
    int_from_word_or_digits,
    sentence_window,
)


def parse_work_mode(text: str) -> dict[str, Any]:
    lower = (text or "").lower()
    hybrid_days = None
    onsite_days = None
    evidence = None
    mode = "UNKNOWN"
    scope = "NOT_STATED"
    remote_allowed_states: list[str] = []
    timezone_requirement = None
    timezone_raw = None

    days_match = re.search(
        r"\b(?P<days>\d+|one|two|three|four|five)\s+days?\s+(?:per\s+week\s+)?(?:in office|onsite|on-site|in-office)",
        text or "",
        re.IGNORECASE,
    )
    if re.search(r"\bhybrid\b", lower) or days_match:
        mode = "HYBRID"
        evidence = sentence_window(text, r"\bhybrid\b|days?\s+(?:per\s+week\s+)?(?:in office|onsite|on-site|in-office)") or compact(days_match.group(0) if days_match else "hybrid")
        if days_match:
            hybrid_days = int_from_word_or_digits(days_match.group("days"))
    elif re.search(r"\b(remote|work from home|wfh)\b", lower):
        mode = "REMOTE"
        evidence = sentence_window(text, r"\b(remote|work from home|wfh)\b")
    elif re.search(r"\b(onsite|on-site|work from office|in office)\b", lower):
        mode = "ONSITE"
        evidence = sentence_window(text, r"\b(onsite|on-site|work from office|in office)\b")

    if mode == "REMOTE":
        if re.search(r"\b(?:within|in)\s+(?:the\s+)?(?:continental\s+)?(?:united states|u\.s\.|us|usa)\b", lower):
            scope = "US_ONLY"
        state_match = re.search(r"\bmust\s+reside\s+in\s+([A-Z][a-z]+|[A-Z]{2})\b", text or "")
        if state_match:
            scope = "STATE_RESTRICTED"
            remote_allowed_states.append(state_match.group(1))

    timezone_match = re.search(r"\b(?:EST|CST|MST|PST|ET|CT|MT|PT|[A-Z][a-z]+ Time)\b", text or "")
    if timezone_match:
        timezone_requirement = timezone_match.group(0)
        timezone_raw = sentence_window(text, re.escape(timezone_requirement)) or timezone_requirement

    return {
        "work_mode": field(mode, status="EXPLICIT" if mode != "UNKNOWN" else "NOT_STATED", evidence=evidence),
        "remote_scope": field(scope, status="EXPLICIT" if scope != "NOT_STATED" else "NOT_STATED", evidence=evidence),
        "remote_allowed_states": remote_allowed_states,
        "remote_excluded_states": [],
        "hybrid_days_per_week": hybrid_days,
        "onsite_days_per_week": onsite_days,
        "timezone_requirement": timezone_requirement,
        "timezone_raw_text": timezone_raw,
    }


def parse_relocation(text: str) -> dict[str, Any]:
    offered = sentence_window(text, r"\brelocation (?:assistance|package|available|offered|provided)\b")
    required = sentence_window(text, r"\brelocation (?:required|is required)\b")
    not_offered = sentence_window(text, r"\b(no relocation (?:assistance|package|available|offered|provided)|relocation is not (?:available|offered|provided))\b")
    if required:
        status, evidence = "REQUIRED", required
    elif offered:
        status, evidence = "OFFERED", offered
    elif not_offered:
        status, evidence = "NOT_OFFERED", not_offered
    else:
        status, evidence = "NOT_STATED", None
    return {
        "relocation_status": field(status, status="EXPLICIT" if evidence else "NOT_STATED", evidence=evidence),
        "relocation_evidence": evidence,
    }


def parse_travel(text: str) -> dict[str, Any]:
    match = re.search(r"\b(?:up to\s+)?(?P<pct>\d{1,3})\s*%\s+travel\b|\btravel\s+(?:up to\s+)?(?P<pct2>\d{1,3})\s*%", text or "", re.IGNORECASE)
    if match:
        pct = int(match.group("pct") or match.group("pct2"))
        raw = compact(match.group(0))
        return {
            "travel_required": True,
            "travel_percentage_min": None,
            "travel_percentage_max": pct,
            "travel_raw_text": raw,
        }
    if re.search(r"\bno travel\b", text or "", re.IGNORECASE):
        return {
            "travel_required": False,
            "travel_percentage_min": None,
            "travel_percentage_max": None,
            "travel_raw_text": sentence_window(text, r"\bno travel\b"),
        }
    return {
        "travel_required": None,
        "travel_percentage_min": None,
        "travel_percentage_max": None,
        "travel_raw_text": None,
    }


def parse_shift(text: str) -> dict[str, Any]:
    lower = (text or "").lower()
    shift = "UNKNOWN"
    if "night shift" in lower:
        shift = "NIGHT"
    elif "evening shift" in lower:
        shift = "EVENING"
    elif "rotating shift" in lower:
        shift = "ROTATING"
    elif "day shift" in lower:
        shift = "DAY"
    elif "flexible hours" in lower:
        shift = "FLEXIBLE"
    weekend = True if re.search(r"\bweekend(?:s)? required\b", lower) else None
    on_call = True if re.search(r"\bon[- ]?call\b", lower) else None
    return {
        "shift_type": unknown(shift) if shift == "UNKNOWN" else field(shift, evidence=sentence_window(text, shift.replace("_", " "))),
        "working_hours_raw": sentence_window(text, r"\b(?:shift|hours|schedule)\b"),
        "weekend_required": weekend,
        "on_call_required": on_call,
    }
