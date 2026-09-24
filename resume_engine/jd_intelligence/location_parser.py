"""Deterministic location parser.

This parser only extracts explicit location text. It does not infer locations
from company headquarters, domains, or remote-role assumptions.
"""

from __future__ import annotations

import re
from typing import Any

from resume_engine.jd_intelligence.schema import (
    STATUS_AMBIGUOUS,
    field,
    not_stated,
)
from resume_engine.jd_intelligence.text_utils import compact

US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "IA": "Iowa",
    "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "MA": "Massachusetts",
    "MD": "Maryland", "ME": "Maine", "MI": "Michigan", "MN": "Minnesota",
    "MO": "Missouri", "MS": "Mississippi", "MT": "Montana",
    "NC": "North Carolina", "ND": "North Dakota", "NE": "Nebraska",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
    "NV": "Nevada", "NY": "New York", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island",
    "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee",
    "TX": "Texas", "UT": "Utah", "VA": "Virginia", "VT": "Vermont",
    "WA": "Washington", "WI": "Wisconsin", "WV": "West Virginia",
    "WY": "Wyoming",
}
STATE_NAMES = {value.lower(): key for key, value in US_STATES.items()}
INDIA_STATES = {
    "andhra pradesh": "AP",
    "delhi": "DL",
    "gujarat": "GJ",
    "haryana": "HR",
    "karnataka": "KA",
    "maharashtra": "MH",
    "tamil nadu": "TN",
    "telangana": "TG",
    "uttar pradesh": "UP",
    "west bengal": "WB",
}
INDIA_STATE_NAMES = {value: key.title() for key, value in INDIA_STATES.items()}

COUNTRIES = {
    "united states": ("United States", "US"),
    "usa": ("United States", "US"),
    "u.s.": ("United States", "US"),
    "us": ("United States", "US"),
    "india": ("India", "IN"),
    "canada": ("Canada", "CA"),
    "united kingdom": ("United Kingdom", "GB"),
    "uk": ("United Kingdom", "GB"),
    "australia": ("Australia", "AU"),
}


def _clean_city(city: str | None) -> str | None:
    if not city:
        return None
    cleaned = re.split(
        r"\b(?:based in|located in|location:?|locations:?|in)\s+",
        city,
        flags=re.IGNORECASE,
    )[-1]
    return cleaned.strip(" :-")


def _us_location(city: str | None, state_code: str | None, raw: str) -> dict[str, Any]:
    state = US_STATES.get(state_code or "")
    country = "United States" if state_code else None
    return {
        "country": country,
        "country_code": "US" if state_code else None,
        "state": state,
        "state_code": state_code,
        "city": _clean_city(city),
        "postal_code": None,
        "location_raw_text": raw,
    }


def _india_location(city: str | None, state_code: str | None, raw: str) -> dict[str, Any]:
    return {
        "country": "India",
        "country_code": "IN",
        "state": INDIA_STATE_NAMES.get(state_code or ""),
        "state_code": state_code,
        "city": _clean_city(city),
        "postal_code": None,
        "location_raw_text": raw,
    }


def _country_is_location_context(text: str, start: int) -> bool:
    window = (text or "")[max(0, start - 80):start].lower()
    if re.search(r"\b(location|locations|located|based|onsite|hybrid|remote|office|role is in)\b", window):
        return True
    if re.search(r"\b(authorized|authorization|eligible|work in|sponsorship|citizen)\b", window):
        return False
    return False


def _location_context_lines(text: str) -> list[str]:
    lines = [compact(line) for line in (text or "").splitlines() if compact(line)]
    out = []
    for line in lines:
        if re.search(
            r"\b(location|locations|located|based|onsite|hybrid|office)\b",
            line,
            re.IGNORECASE,
        ) and not re.search(
            r"\b(authorized|authorization|sponsorship|citizen|eligible)\b",
            line,
            re.IGNORECASE,
        ):
            out.append(line)
    return out


def _state_only_location(text: str) -> dict[str, Any] | None:
    for line in _location_context_lines(text):
        candidate = re.sub(r"^(?:location|locations)\s*:\s*", "", line, flags=re.IGNORECASE).strip()
        lower = candidate.lower()
        us_code = STATE_NAMES.get(lower)
        if us_code:
            return _us_location(None, us_code, line)
        india_code = INDIA_STATES.get(lower)
        if india_code:
            return _india_location(None, india_code, line)
    return None


def _single_city_location(text: str) -> tuple[dict[str, Any] | None, str | None]:
    for line in _location_context_lines(text):
        candidate = re.sub(r"^(?:location|locations)\s*:\s*", "", line, flags=re.IGNORECASE).strip()
        if not re.fullmatch(r"[A-Z][A-Za-z .'-]{1,45}", candidate):
            continue
        return (
            {
                "country": None,
                "country_code": None,
                "state": None,
                "state_code": None,
                "city": candidate,
                "postal_code": None,
                "location_raw_text": line,
                "status": STATUS_AMBIGUOUS,
            },
            "LOCATION_NEEDS_REVIEW_SINGLE_CITY",
        )
    return None, None


def parse_location(text: str) -> dict[str, Any]:
    found: list[dict[str, Any]] = []
    warning = None
    # City, ST patterns. Avoid matching technology lists by requiring known state code.
    for match in re.finditer(r"\b([A-Z][A-Za-z .'-]{1,45}),\s*([A-Z]{2})\b", text or ""):
        code = match.group(2).upper()
        if code not in US_STATES:
            continue
        found.append(_us_location(match.group(1), code, compact(match.group(0))))

    # City, State Name patterns for US and India.
    for match in re.finditer(r"\b([A-Z][A-Za-z .'-]{1,45}),\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b", text or ""):
        state_text = match.group(2).lower()
        raw = compact(match.group(0))
        us_code = STATE_NAMES.get(state_text)
        india_code = INDIA_STATES.get(state_text)
        if us_code:
            location = _us_location(match.group(1), us_code, raw)
        elif india_code:
            location = _india_location(match.group(1), india_code, raw)
        else:
            continue
        if not any(item["location_raw_text"] == raw for item in found):
            found.append(location)

    country = country_code = None
    country_evidence = None
    for token, (name, code) in COUNTRIES.items():
        match = re.search(rf"\b{re.escape(token)}\b", text or "", re.IGNORECASE)
        if match and _country_is_location_context(text or "", match.start()):
            country, country_code = name, code
            country_evidence = compact(match.group(0))
            break

    first = found[0] if found else {}
    if not found and country:
        first = {
            "country": country,
            "country_code": country_code,
            "state": None,
            "state_code": None,
            "city": None,
            "postal_code": None,
            "location_raw_text": country_evidence,
        }
    elif not found:
        state_only = _state_only_location(text or "")
        if state_only:
            first = state_only
        else:
            single_city, warning = _single_city_location(text or "")
            if single_city:
                first = single_city

    status = first.get("status") or "EXPLICIT"
    location_needs_review = status == STATUS_AMBIGUOUS or bool(warning)

    return {
        "country": field(first.get("country"), status=status, evidence=first.get("location_raw_text")) if first.get("country") else not_stated(None),
        "country_code": first.get("country_code"),
        "state": field(first.get("state"), status=status, evidence=first.get("location_raw_text")) if first.get("state") else not_stated(None),
        "state_code": first.get("state_code"),
        "city": field(first.get("city"), status=status, evidence=first.get("location_raw_text")) if first.get("city") else not_stated(None),
        "postal_code": first.get("postal_code"),
        "location_raw_text": first.get("location_raw_text"),
        "multiple_locations": found,
        "location_needs_review": location_needs_review,
        "location_review_reason": warning,
    }
