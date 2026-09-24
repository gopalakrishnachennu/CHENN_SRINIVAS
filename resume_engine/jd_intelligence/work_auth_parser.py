"""Work authorization and visa parsing."""

from __future__ import annotations

import re
from typing import Any

from resume_engine.jd_intelligence.schema import field
from resume_engine.jd_intelligence.text_utils import sentence_window


def parse_work_auth(text: str) -> dict[str, Any]:
    sponsorship = "SPONSORSHIP_NOT_STATED"
    sponsorship_evidence = None
    authorization = "NONE_STATED"
    authorization_evidence = None
    student = "OPT_CPT_NOT_STATED"
    h1b = "NOT_STATED"
    ead = "NOT_STATED"

    no_spon = sentence_window(text, r"\b(no|cannot|unable to|will not)\s+(?:provide\s+)?sponsorship\b|\bno sponsorship\b")
    if no_spon:
        sponsorship = "NO_SPONSORSHIP"
        sponsorship_evidence = no_spon
    else:
        available = sentence_window(text, r"\bsponsorship (?:available|provided|offered)\b")
        if available:
            sponsorship = "SPONSORSHIP_AVAILABLE"
            sponsorship_evidence = available

    citizen = sentence_window(text, r"\bUS citizen(?:ship)? only\b|\bmust be (?:a )?US citizen\b")
    gc = sentence_window(text, r"\b(?:green card|permanent resident|GC)/(?:citizen|US citizen)\b|\b(?:US citizen|green card)(?:s)? only\b")
    authorized = sentence_window(text, r"\bauthorized to work in (?:the )?(?:United States|US|U\.S\.)\b")
    if citizen:
        authorization = "US_CITIZEN_ONLY"
        authorization_evidence = citizen
    elif gc:
        authorization = "US_CITIZEN_OR_GREEN_CARD"
        authorization_evidence = gc
    elif authorized:
        authorization = "AUTHORIZED_TO_WORK_US"
        authorization_evidence = authorized

    opt_cpt_allowed = sentence_window(text, r"\bOPT\b.*\bCPT\b|\bCPT\b.*\bOPT\b")
    if opt_cpt_allowed and not re.search(r"\bnot\s+(?:accept|allow|eligible).{0,40}\b(?:OPT|CPT)\b", opt_cpt_allowed, re.IGNORECASE):
        student = "OPT_CPT_ALLOWED"
    elif sentence_window(text, r"\bOPT\b"):
        student = "OPT_ONLY_ALLOWED"
    elif sentence_window(text, r"\bCPT\b"):
        student = "CPT_ONLY_ALLOWED"
    if sentence_window(text, r"\b(?:no|not eligible|not accepted).{0,40}\b(?:OPT|CPT)\b"):
        student = "OPT_CPT_NOT_ALLOWED"

    if sentence_window(text, r"\bH-?1B\b.{0,40}\b(?:supported|sponsorship|transfer)\b"):
        h1b = "SUPPORTED"
    if sentence_window(text, r"\bH-?1B\b.{0,40}\btransfer\b"):
        h1b = "TRANSFER_ONLY"
    if sentence_window(text, r"\b(?:no|not).{0,40}\bH-?1B\b|\bH-?1B\b.{0,40}\bnot\b"):
        h1b = "NOT_SUPPORTED"

    if sentence_window(text, r"\bEAD\b.{0,40}\b(?:accepted|eligible|allowed)\b"):
        ead = "ACCEPTED"
    if sentence_window(text, r"\bEAD\b.{0,40}\bnot\b|\bno\s+EAD\b"):
        ead = "NOT_ACCEPTED"

    return {
        "sponsorship_status": field(sponsorship, status="EXPLICIT" if sponsorship_evidence else "NOT_STATED", evidence=sponsorship_evidence),
        "authorization_requirement": field(authorization, status="EXPLICIT" if authorization_evidence else "NOT_STATED", evidence=authorization_evidence),
        "student_visa_status": field(student, status="EXPLICIT" if student != "OPT_CPT_NOT_STATED" else "NOT_STATED", evidence=sentence_window(text, r"\b(?:OPT|CPT)\b")),
        "h1b_status": field(h1b, status="EXPLICIT" if h1b != "NOT_STATED" else "NOT_STATED", evidence=sentence_window(text, r"\bH-?1B\b")),
        "ead_status": field(ead, status="EXPLICIT" if ead != "NOT_STATED" else "NOT_STATED", evidence=sentence_window(text, r"\bEAD\b")),
    }
