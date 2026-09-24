"""Posting date parser."""

from __future__ import annotations

from typing import Any

from resume_engine.jd_intelligence.schema import not_stated


def parse_dates(text: str) -> dict[str, Any]:
    # Keep conservative: only expose fields when future normalization is added.
    return {
        "posting_date": not_stated(None),
        "closing_date": not_stated(None),
        "last_updated_date": not_stated(None),
    }
