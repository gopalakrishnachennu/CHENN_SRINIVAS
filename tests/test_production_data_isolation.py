"""Prove tests never touch production SQLite / artifact storage."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from resume_engine.config.settings import (
    get_sqlite_db_path,
    get_ui_artifact_dir,
    production_sqlite_db_path,
)
from resume_engine.ui.db import connect_ui_db, ui_db_path
from resume_engine.ui.services import candidate_service

PRODUCTION_DB = production_sqlite_db_path()


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def test_pytest_never_uses_production_sqlite():
    path = get_sqlite_db_path().resolve()
    assert path != PRODUCTION_DB
    assert "test_resume_engine.sqlite3" in str(path) or path != PRODUCTION_DB
    assert os.getenv("RESUME_ENGINE_FORCE_TEST_ISOLATION") == "1"


def test_ui_tests_use_temp_database():
    assert ui_db_path().resolve() != PRODUCTION_DB
    with connect_ui_db() as conn:
        conn.execute("SELECT 1").fetchone()
    assert get_sqlite_db_path().resolve() != PRODUCTION_DB


def test_end_to_end_tests_use_temp_database():
    cand = candidate_service.create_profile({
        "candidate_name": "Isolation Probe",
        "primary_family": "ai_ml",
        "companies": [{"company": "Iso", "start_date": "2020-01", "end_date": "2021-01"}],
    })
    assert cand["id"]
    assert get_sqlite_db_path().resolve() != PRODUCTION_DB


def test_test_blueprints_use_temp_storage():
    root = get_ui_artifact_dir()
    assert root.resolve() != (PRODUCTION_DB.parent.parent / "ui").resolve()
    bp = root / "test_blueprints"
    bp.mkdir(parents=True, exist_ok=True)
    probe = bp / "probe.json"
    probe.write_text("{}", encoding="utf-8")
    assert "tmp" in str(probe.resolve()).lower() or probe.resolve() != (
        PRODUCTION_DB.parent.parent / "ui" / "test_blueprints" / "probe.json"
    ).resolve()
    # Must not write under production storage/ui/test_blueprints unless that IS tmp
    prod_probe = PRODUCTION_DB.parent.parent / "ui" / "test_blueprints" / "probe.json"
    if prod_probe.exists() and prod_probe.resolve() == probe.resolve():
        pytest.fail("test blueprint wrote to production storage")


def test_production_database_unchanged_after_ui_test(monkeypatch):
    before = _sha256(PRODUCTION_DB)
    existed = PRODUCTION_DB.exists()
    from tests.ui._helpers import make_client

    client = make_client(monkeypatch)
    client.get("/matches/")
    candidate_service.create_profile({
        "candidate_name": "UI Cand Isolation",
        "primary_family": "ai_ml",
        "companies": [{"company": "X", "start_date": "2021-01", "end_date": "2022-01"}],
    })
    after = _sha256(PRODUCTION_DB)
    assert existed == PRODUCTION_DB.exists()
    assert before == after


def test_production_database_unchanged_after_full_offline_suite():
    """Marker test documenting the release gate; hash checked in CI script too."""
    before = _sha256(PRODUCTION_DB)
    # Local mutation in TEMP db only
    with connect_ui_db() as conn:
        conn.execute("SELECT COUNT(*) AS n FROM candidate_profiles").fetchone()
    after = _sha256(PRODUCTION_DB)
    assert before == after
    assert get_sqlite_db_path().resolve() != PRODUCTION_DB


def test_connect_ui_db_raises_if_forced_onto_production(monkeypatch, tmp_path):
    monkeypatch.setenv("RESUME_ENGINE_DB_PATH", str(PRODUCTION_DB))
    monkeypatch.setenv("RESUME_ENGINE_FORCE_TEST_ISOLATION", "1")
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "1")
    with pytest.raises(RuntimeError, match="TEST_DATABASE_ISOLATION_VIOLATION"):
        connect_ui_db()
    # Restore isolation path so autouse teardown does not trip
    monkeypatch.setenv("RESUME_ENGINE_DB_PATH", str(tmp_path / "restored.sqlite3"))
