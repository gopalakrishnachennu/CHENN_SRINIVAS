"""Deterministic salary parser for Phase 3.3 JD intelligence."""

from __future__ import annotations

import re
from typing import Any

from resume_engine.jd_intelligence.schema import field, not_stated
from resume_engine.jd_intelligence.text_utils import compact

CURRENCY_SYMBOLS = {
    "$": "USD",
    "₹": "INR",
    "£": "GBP",
    "€": "EUR",
}

CURRENCY_WORDS = {
    "USD": "USD",
    "INR": "INR",
    "GBP": "GBP",
    "EUR": "EUR",
    "CAD": "CAD",
    "AUD": "AUD",
}


def _normalize_amount(raw: str) -> float:
    value = raw.replace(",", "").strip().lower()
    multiplier = 1
    if value.endswith("k"):
        multiplier = 1000
        value = value[:-1]
    elif value.endswith("l"):
        multiplier = 100000
        value = value[:-1]
    elif value.endswith(("lakh", "lakhs")):
        multiplier = 100000
        value = re.sub(r"lakhs?$", "", value).strip()
    return float(value) * multiplier


def _period(raw: str) -> str:
    lower = raw.lower()
    if re.search(r"\b(hour|hr|hourly)\b|/hr|/hour", lower):
        return "HOURLY"
    if re.search(r"\b(day|daily)\b|/day", lower):
        return "DAILY"
    if re.search(r"\b(week|weekly)\b|/week", lower):
        return "WEEKLY"
    if re.search(r"\b(month|monthly)\b|/month", lower):
        return "MONTHLY"
    if re.search(r"\b(annual|annually|year|yearly|per annum)\b", lower):
        return "ANNUAL"
    return "UNKNOWN"


def _currency(raw: str) -> str | None:
    for symbol, code in CURRENCY_SYMBOLS.items():
        if symbol in raw:
            return code
    upper = raw.upper()
    for word, code in CURRENCY_WORDS.items():
        if re.search(rf"\b{word}\b", upper):
            return code
    return None


def parse_salary(text: str) -> dict[str, Any]:
    """Parse stated compensation without currency conversion."""
    patterns = [
        r"(?P<cur>[$₹£€]|USD|INR|GBP|EUR|CAD|AUD)?\s*(?P<min>\d[\d,]*(?:\.\d+)?\s*(?:k|K|lakh|lakhs|L)?)\s*(?:-|to|–|—)\s*(?P<cur2>[$₹£€]|USD|INR|GBP|EUR|CAD|AUD)?\s*(?P<max>\d[\d,]*(?:\.\d+)?\s*(?:k|K|lakh|lakhs|L)?)\s*(?P<period>/\s*(?:hr|hour|day|week|month)|hourly|annually|annual|per year|yearly)?",
        r"(?P<cur>[$₹£€]|USD|INR|GBP|EUR|CAD|AUD)\s*(?P<single>\d[\d,]*(?:\.\d+)?\s*(?:k|K|lakh|lakhs|L)?)\s*(?P<period>/\s*(?:hr|hour|day|week|month)|hourly|annually|annual|per year|yearly)?",
    ]
    for pattern in patterns:
        match = re.search(pattern, text or "", re.IGNORECASE)
        if not match:
            continue
        raw = compact(match.group(0))
        code = _currency(raw)
        if not code:
            continue
        if match.groupdict().get("single"):
            minimum = maximum = _normalize_amount(match.group("single"))
        else:
            minimum = _normalize_amount(match.group("min"))
            maximum = _normalize_amount(match.group("max"))
        if minimum > maximum:
            minimum, maximum = maximum, minimum
        return {
            "salary_status": field("STATED", evidence=raw),
            "salary_min": minimum,
            "salary_max": maximum,
            "salary_currency": code,
            "salary_period": _period(raw),
            "base_salary_min": minimum,
            "base_salary_max": maximum,
            "total_compensation_min": None,
            "total_compensation_max": None,
            "compensation_raw_text": raw,
            "compensation_evidence": [raw],
            "bonus_available": None,
            "bonus_raw_text": None,
            "commission_available": None,
            "commission_raw_text": None,
            "equity_available": None,
            "equity_type": None,
            "sign_on_bonus_available": None,
        }
    return {
        "salary_status": not_stated("NOT_STATED"),
        "salary_min": None,
        "salary_max": None,
        "salary_currency": None,
        "salary_period": "UNKNOWN",
        "base_salary_min": None,
        "base_salary_max": None,
        "total_compensation_min": None,
        "total_compensation_max": None,
        "compensation_raw_text": None,
        "compensation_evidence": [],
        "bonus_available": None,
        "bonus_raw_text": None,
        "commission_available": None,
        "commission_raw_text": None,
        "equity_available": None,
        "equity_type": None,
        "sign_on_bonus_available": None,
    }
