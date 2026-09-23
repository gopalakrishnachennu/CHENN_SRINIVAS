"""Opt-in live Phase 1 harness (Gate 4 / 4.1).

Does NOT run unless:
  RUN_LIVE_TESTS=1
  OPENAI_API_KEY is set and not a placeholder

Never logs the API key. Designed for explicit paid verification only.

Gate 4.1: all registry/blueprint/evidence writes go under
resume_engine/storage/reports/live/<live_run_id>/ — never mutates the
normal skill registry, blueprint store, or jd history.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

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
    openai_live: str
    laya_live: str
    full_phase1_live_e2e: str
    blueprint_path: str | None
    primary_family: str | None
    p1: list[str]
    allowed_technologies: list[str]
    model: str
    created_at: str
    message: str
    live_run_id: str | None = None
    live_run_dir: str | None = None
    registry_path: str | None = None
    default_registry_unchanged: bool | None = None


def live_tests_requested() -> bool:
    return os.getenv("RUN_LIVE_TESTS", "").strip() == "1"


def openai_credentials_present() -> bool:
    load_local_environment()
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        return False
    return not key.upper().startswith("PASTE_")


def preflight_live_harness() -> tuple[bool, str]:
    """Return (ok, reason). Never contacts OpenAI. Never writes files."""
    if not live_tests_requested():
        return False, "LIVE_TEST_NOT_RUN: set RUN_LIVE_TESTS=1"
    if not openai_credentials_present():
        return False, "LIVE_TEST_NOT_RUN: OPENAI_API_KEY missing or placeholder"
    return True, "ready"


def _file_sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _prepare_live_registry(live_registry: Path) -> None:
    """Seed isolated registry from production copy or seed — never writes prod."""
    from jd_blueprint_engine import REGISTRY_FILE, SEED_REGISTRY

    live_registry.parent.mkdir(parents=True, exist_ok=True)
    if REGISTRY_FILE.exists():
        shutil.copy2(REGISTRY_FILE, live_registry)
    else:
        with open(live_registry, "w", encoding="utf-8") as f:
            json.dump(json.loads(json.dumps(SEED_REGISTRY)), f, indent=2)


def run_phase1_live_harness(
    *,
    jd_text: str | None = None,
    skip_laya: bool = False,
    registry_path: Path | None = None,
    blueprint_dir: Path | None = None,
    live_run_id: str | None = None,
) -> LiveHarnessResult:
    """
    Execute Phase 1 extract → blueprint (optional Laya) against a short JD.

    Storage is isolated under reports/live/<run_id>/ unless explicit paths
    are provided. Raises if preflight fails.
    """
    ok, reason = preflight_live_harness()
    if not ok:
        raise RuntimeError(reason)

    ensure_storage_dirs()
    load_local_environment()
    model = os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)

    from openai import OpenAI

    from jd_blueprint_engine import (
        REGISTRY_FILE,
        build_blueprint,
        extract_jd,
        load_laya_agent,
        load_registry,
        save_blueprint,
        update_registry_from_jd,
    )

    run_id = live_run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    live_dir = Path(blueprint_dir) if blueprint_dir is not None else (REPORT_STORAGE_DIR / "live" / run_id)
    live_dir.mkdir(parents=True, exist_ok=True)
    live_registry = Path(registry_path) if registry_path is not None else (live_dir / "registry.json")

    before_hash = _file_sha256(REGISTRY_FILE)
    _prepare_live_registry(live_registry)

    client = OpenAI()
    text = (jd_text or LIVE_JD_FIXTURE).strip()
    extraction = extract_jd(text, client)
    registry = load_registry(live_registry)
    registry = update_registry_from_jd(extraction, registry, registry_path=live_registry)

    laya_status = "SKIPPED"
    laya_agent = None
    if skip_laya:
        laya_status = "SKIPPED"
    else:
        laya_agent = load_laya_agent()
        laya_status = "PASS"

    blueprint = build_blueprint(text, extraction, registry, laya_agent)
    blueprint_path = save_blueprint(
        blueprint,
        blueprint_dir=live_dir,
        write_history=False,
        filename="blueprint.json",
    )

    after_hash = _file_sha256(REGISTRY_FILE)
    registry_unchanged = before_hash == after_hash

    p1 = list((blueprint.get("priority_skills") or {}).get("P1") or [])
    allowed = list(
        (blueprint.get("generation_contract") or {}).get("allowed_technologies") or []
    )

    openai_status = "PASS"
    message = "Phase 1 live harness completed (isolated storage)"
    if not p1:
        openai_status = "FAIL"
        message = "Live blueprint missing P1 skills"
    elif not any("aws" in t.lower() for t in allowed):
        openai_status = "FAIL"
        message = "Live blueprint missing AWS in allowed_technologies"

    if openai_status != "PASS":
        status = "FAIL"
        full_e2e = "FAIL"
    elif skip_laya:
        status = "PASS_OPENAI_LAYA_SKIPPED"
        full_e2e = "SKIPPED"
        message = "OpenAI live: PASS; Laya live: SKIPPED (not full Phase 1 E2E)"
    else:
        status = "PASS"
        full_e2e = "PASS"
        message = "OpenAI live: PASS; Laya live: PASS; Full Phase 1 live E2E: PASS"

    if not registry_unchanged:
        status = "FAIL"
        message = "Default skill registry was modified during live harness"
        full_e2e = "FAIL"

    result = LiveHarnessResult(
        status=status,
        openai_live=openai_status,
        laya_live=laya_status if openai_status == "PASS" else ("SKIPPED" if skip_laya else "FAIL"),
        full_phase1_live_e2e=full_e2e,
        blueprint_path=portable_path(blueprint_path),
        primary_family=(blueprint.get("job") or {}).get("primary_family"),
        p1=p1,
        allowed_technologies=allowed,
        model=model,
        created_at=datetime.now(UTC).isoformat(),
        message=message,
        live_run_id=run_id,
        live_run_dir=portable_path(live_dir),
        registry_path=portable_path(live_registry),
        default_registry_unchanged=registry_unchanged,
    )
    evidence = live_dir / "evidence.json"
    with open(evidence, "w", encoding="utf-8") as f:
        json.dump(asdict(result), f, indent=2, ensure_ascii=False)
    return result
