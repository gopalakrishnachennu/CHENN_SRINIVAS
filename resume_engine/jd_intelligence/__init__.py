"""Phase 3.3 JD intelligence package.

Deterministic parsers live here so JD facts can be extracted and tested without
browser automation, scraping, or live model calls.
"""

from resume_engine.jd_intelligence.schema import JOB_INTELLIGENCE_SCHEMA_VERSION

__all__ = ["JOB_INTELLIGENCE_SCHEMA_VERSION"]
