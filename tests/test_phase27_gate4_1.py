"""
Phase 2.7 Gate 4.1 — live isolation, safe redirects, path containment.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from resume_engine.config import settings
from resume_engine.live.phase1_harness import preflight_live_harness, run_phase1_live_harness
from resume_engine.ui.app import create_app
from resume_engine.ui.auth import safe_next_url
from resume_engine.ui.paths import InvalidResumePath, resolve_validated_resume_path


def _fake_extraction():
    return SimpleNamespace(
        entities=[
            SimpleNamespace(name="AWS", category="cloud", requirement="required", evidence="AWS"),
            SimpleNamespace(
                name="Terraform", category="devops", requirement="required", evidence="Terraform"
            ),
        ]
    )


def _fake_blueprint() -> dict:
    return {
        "jd_hash": "livehash",
        "created_at": "2026-01-01T00:00:00Z",
        "job": {
            "target_title": "Senior Cloud Platform Engineer",
            "primary_family": "devops_cloud",
            "secondary_family": "none",
        },
        "priority_skills": {"P1": ["AWS", "Terraform"], "P2": [], "P3": [], "P4": []},
        "generation_contract": {"allowed_technologies": ["AWS", "Terraform", "Kubernetes"]},
    }


def _enable_live_preflight(monkeypatch):
    monkeypatch.setenv("RUN_LIVE_TESTS", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real-but-present")


def _patch_phase1(monkeypatch, tmp_path: Path):
    """Mock OpenAI + Phase 1 functions; keep registry/blueprint path injection real."""
    import jd_blueprint_engine as jbe
    import resume_engine.live.phase1_harness as harness

    monkeypatch.setattr(harness, "REPORT_STORAGE_DIR", tmp_path / "reports")
    monkeypatch.setattr(jbe, "REGISTRY_FILE", tmp_path / "prod_skill_registry.json")
    # Seed a production registry that must remain unchanged.
    prod = {"existing": {"canonical": "Existing", "category": "other", "adjacent": [], "seen": 1}}
    jbe.REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    jbe.REGISTRY_FILE.write_text(json.dumps(prod), encoding="utf-8")

    monkeypatch.setattr(
        "openai.OpenAI",
        lambda *a, **k: MagicMock(),
    )
    monkeypatch.setattr(jbe, "extract_jd", lambda text, client: _fake_extraction())
    monkeypatch.setattr(
        jbe,
        "build_blueprint",
        lambda text, extraction, registry, laya_agent: _fake_blueprint(),
    )
    monkeypatch.setattr(jbe, "load_laya_agent", lambda: object())
    return jbe.REGISTRY_FILE


# ---------------------------------------------------------------------------
# Live harness isolation
# ---------------------------------------------------------------------------


def test_live_harness_preflight_does_not_write_files(tmp_path, monkeypatch):
    monkeypatch.delenv("RUN_LIVE_TESTS", raising=False)
    before = {p.name for p in tmp_path.iterdir()} if tmp_path.exists() else set()
    ok, reason = preflight_live_harness()
    assert ok is False
    assert "LIVE_TEST_NOT_RUN" in reason
    after = {p.name for p in tmp_path.iterdir()} if tmp_path.exists() else set()
    assert before == after


def test_live_harness_uses_isolated_registry(tmp_path, monkeypatch):
    _enable_live_preflight(monkeypatch)
    prod = _patch_phase1(monkeypatch, tmp_path)
    before = hashlib.sha256(prod.read_bytes()).hexdigest()

    result = run_phase1_live_harness(skip_laya=True, live_run_id="iso1")
    assert result.registry_path is not None
    live_reg = Path(tmp_path / "reports" / "live" / "iso1" / "registry.json")
    assert live_reg.exists()
    assert live_reg.resolve() != prod.resolve()
    assert hashlib.sha256(prod.read_bytes()).hexdigest() == before
    assert result.default_registry_unchanged is True


def test_live_harness_does_not_modify_default_registry(tmp_path, monkeypatch):
    _enable_live_preflight(monkeypatch)
    prod = _patch_phase1(monkeypatch, tmp_path)
    before = prod.read_text(encoding="utf-8")
    result = run_phase1_live_harness(skip_laya=True, live_run_id="iso2")
    assert prod.read_text(encoding="utf-8") == before
    assert result.default_registry_unchanged is True
    # Isolated registry should have been updated with JD entities.
    live_reg = json.loads((tmp_path / "reports" / "live" / "iso2" / "registry.json").read_text())
    assert any("aws" in k for k in live_reg)


def test_live_harness_blueprint_written_under_live_storage(tmp_path, monkeypatch):
    _enable_live_preflight(monkeypatch)
    _patch_phase1(monkeypatch, tmp_path)
    result = run_phase1_live_harness(skip_laya=True, live_run_id="iso3")
    live_dir = tmp_path / "reports" / "live" / "iso3"
    assert (live_dir / "blueprint.json").exists()
    assert (live_dir / "evidence.json").exists()
    assert (live_dir / "registry.json").exists()
    assert "live" in (result.blueprint_path or "")
    assert result.openai_live == "PASS"
    assert result.laya_live == "SKIPPED"
    assert result.full_phase1_live_e2e == "SKIPPED"
    assert result.status == "PASS_OPENAI_LAYA_SKIPPED"


# ---------------------------------------------------------------------------
# Safe redirects
# ---------------------------------------------------------------------------


def test_login_next_local_path_allowed(monkeypatch):
    monkeypatch.setenv("RESUME_ENGINE_UI_PASSWORD", "s3cret")
    app = create_app()
    with app.test_request_context():
        assert safe_next_url("/view?path=x") == "/view?path=x"
        assert safe_next_url("/") == "/"


def test_login_next_external_url_rejected(monkeypatch):
    monkeypatch.setenv("RESUME_ENGINE_UI_PASSWORD", "s3cret")
    app = create_app()
    with app.test_request_context():
        assert safe_next_url("https://evil.example") in {"/", app.url_for("dashboard.index")}


def test_login_next_protocol_relative_rejected(monkeypatch):
    monkeypatch.setenv("RESUME_ENGINE_UI_PASSWORD", "s3cret")
    app = create_app()
    with app.test_request_context():
        assert safe_next_url("//evil.example") == "/"


def test_login_next_javascript_rejected(monkeypatch):
    monkeypatch.setenv("RESUME_ENGINE_UI_PASSWORD", "s3cret")
    app = create_app()
    with app.test_request_context():
        assert safe_next_url("javascript:alert(1)") == "/"


def test_login_next_missing_defaults_index(monkeypatch):
    monkeypatch.setenv("RESUME_ENGINE_UI_PASSWORD", "s3cret")
    monkeypatch.setenv("RESUME_ENGINE_UI_USER", "operator")
    client = create_app().test_client()
    login_page = client.get("/login")
    import re

    html = login_page.data.decode("utf-8", errors="ignore")
    match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert match
    response = client.post(
        "/login",
        data={
            "username": "operator",
            "password": "s3cret",
            "csrf_token": match.group(1),
        },
        follow_redirects=False,
    )
    assert response.status_code in {302, 303}
    assert response.headers.get("Location", "").endswith("/")


# ---------------------------------------------------------------------------
# Path containment
# ---------------------------------------------------------------------------


def _seed_validated(tmp_path: Path, monkeypatch) -> Path:
    runs = tmp_path / "runs"
    monkeypatch.setattr(settings, "RUNS_STORAGE_DIR", runs)
    monkeypatch.setattr(settings, "PROJECT_ROOT", tmp_path)
    # Also patch the module used by resolve helper.
    import resume_engine.ui.paths as paths_mod

    monkeypatch.setattr(paths_mod, "RUNS_STORAGE_DIR", runs)
    target = runs / "jd1" / "run1" / "validated" / "V01_final.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('{"target_title":"x","summary":"y","technical_skills":{},'
                      '"experience":[],"projects":[],"certifications":[],"variant_id":"V01"}',
                      encoding="utf-8")
    return target


def test_validated_path_inside_runs_allowed(tmp_path, monkeypatch):
    target = _seed_validated(tmp_path, monkeypatch)
    import resume_engine.ui.paths as paths_mod

    monkeypatch.setattr(paths_mod, "PROJECT_ROOT", tmp_path, raising=False)
    # relative from project root
    rel = target.relative_to(tmp_path).as_posix()
    resolved = resolve_validated_resume_path(rel)
    assert resolved == target.resolve()


def test_path_traversal_rejected(tmp_path, monkeypatch):
    _seed_validated(tmp_path, monkeypatch)
    with pytest.raises(InvalidResumePath):
        resolve_validated_resume_path("../../etc/passwd")


def test_prefix_collision_path_rejected(tmp_path, monkeypatch):
    _seed_validated(tmp_path, monkeypatch)
    evil = tmp_path / "runs_evil" / "file.json"
    evil.parent.mkdir(parents=True, exist_ok=True)
    evil.write_text("{}", encoding="utf-8")
    with pytest.raises(InvalidResumePath):
        resolve_validated_resume_path("runs_evil/file.json")


def test_absolute_external_path_rejected(tmp_path, monkeypatch):
    _seed_validated(tmp_path, monkeypatch)
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    with pytest.raises(InvalidResumePath):
        resolve_validated_resume_path(str(outside.resolve()))


def test_symlink_escape_rejected_if_supported(tmp_path, monkeypatch):
    target = _seed_validated(tmp_path, monkeypatch)
    outside = tmp_path / "secret.json"
    outside.write_text("{}", encoding="utf-8")
    link = target.parent / "escape.json"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported")
    rel = link.relative_to(tmp_path).as_posix()
    with pytest.raises(InvalidResumePath):
        resolve_validated_resume_path(rel)


def test_nonexistent_path_rejected(tmp_path, monkeypatch):
    _seed_validated(tmp_path, monkeypatch)
    with pytest.raises(InvalidResumePath):
        resolve_validated_resume_path("runs/jd1/run1/validated/missing.json")
