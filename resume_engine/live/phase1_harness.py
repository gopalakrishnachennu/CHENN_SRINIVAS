"""Opt-in live Phase 1 harness (Gate 4).

Does NOT run unless:
  RUN_LIVE_TESTS=1
  OPENAI_API_KEY is set and not a placeholder

Never logs the API key. Designed for explicit paid verification only.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from resume_engine.config.settings import (
    DEFAULT_OPENAI_MODEL,
    REPORT_STORAGE_DIR,
    ensure_storage_dirs,
    load_local_environment,
    portable_path,
)

LIVE_JD_FIXTURE = """Role: Senior Cloud Platform Engineer

We need an engineer to run AWS infrastructure with Terraform and Kubernetes.
Required skills: AWS, Terraform, Kubernetes, Python, CI/CD.
Responsibilities:
- Deploy and maintain Kubernetes on AWS using Terraform
- Automate CI/CD release pipelines with Python
"""


@dataclass
class LiveHarnessResult:
    status: str
    blueprint_path: str | None
    primary_family: str | None
    p1: list[str]
    allowed_technologies: list[str]
    model: str
    created_at: str
    message: str


def live_tests_requested() -> bool:
    return os.getenv("RUN_LIVE_TESTS", "").strip() == "1"


def openai_credentials_present() -> bool:
    load_local_environment()
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        return False
    if key.upper().startswith("PASTE_"):
        return False
    return True


def preflight_live_harness() -> tuple[bool, str]:
    """Return (ok, reason). Never contacts OpenAI."""
    if not live_tests_requested():
        return False, "LIVE_TEST_NOT_RUN: set RUN_LIVE_TESTS=1"
    if not openai_credentials_present():
        return False, "LIVE_TEST_NOT_RUN: OPENAI_API_KEY missing or placeholder"
    return True, "ready"


def run_phase1_live_harness(
    *,
    jd_text: str | None = None,
    skip_laya: bool = False,
) -> LiveHarnessResult:
    """
    Execute Phase 1 extract → blueprint (optional Laya) against a short JD.

    Raises if preflight fails. Caller (pytest) should skip before calling
    when credentials are absent.
    """
    ok, reason = preflight_live_harness()
    if not ok:
        raise RuntimeError(reason)

    ensure_storage_dirs()
    load_local_environment()
    model = os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)

    from openai import OpenAI

    from jd_blueprint_engine import (
        build_blueprint,
        extract_jd,
        load_laya_agent,
        load_registry,
        save_blueprint,
        update_registry_from_jd,
    )

    client = OpenAI()
    text = (jd_text or LIVE_JD_FIXTURE).strip()
    extraction = extract_jd(text, client)
    registry = update_registry_from_jd(extraction, load_registry())
    laya_agent = None if skip_laya else load_laya_agent()
    blueprint = build_blueprint(text, extraction, registry, laya_agent)
    blueprint_path = save_blueprint(blueprint)

    live_dir = REPORT_STORAGE_DIR / "live"
    live_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence = live_dir / f"phase1_live_{stamp}.json"

    p1 = list((blueprint.get("priority_skills") or {}).get("P1") or [])
    allowed = list(
        (blueprint.get("generation_contract") or {}).get("allowed_technologies") or []
    )
    status = "PASS"
    message = "Phase 1 live harness completed"
    if not p1:
        status = "FAIL"
        message = "Live blueprint missing P1 skills"
    elif not any("aws" in t.lower() for t in allowed):
        status = "FAIL"
        message = "Live blueprint missing AWS in allowed_technologies"

    result = LiveHarnessResult(
        status=status,
        blueprint_path=portable_path(blueprint_path),
        primary_family=(blueprint.get("job") or {}).get("primary_family"),
        p1=p1,
        allowed_technologies=allowed,
        model=model,
        created_at=datetime.now(timezone.utc).isoformat(),
        message=message,
    )
    with open(evidence, "w", encoding="utf-8") as f:
        json.dump(asdict(result), f, indent=2, ensure_ascii=False)
    return result
