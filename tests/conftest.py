"""
pytest conftest: absolute test isolation from production SQLite / UI storage.

Every test gets a temporary SQLite DB and UI artifact root. Production
`resume_engine/storage/db/resume_engine.sqlite3` must never be opened.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Ensure project root is importable even when running pytest from sub-dirs
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

PRODUCTION_DB = (
    PROJECT_ROOT / "resume_engine" / "storage" / "db" / "resume_engine.sqlite3"
).resolve()


@pytest.fixture(autouse=True)
def _isolate_resume_engine_storage(tmp_path, monkeypatch):
    """Force all DB/UI writes into tmp_path for the duration of each test."""
    test_db = tmp_path / "test_resume_engine.sqlite3"
    ui_root = tmp_path / "ui_storage"
    ui_root.mkdir(parents=True, exist_ok=True)
    (ui_root / "test_blueprints").mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("RESUME_ENGINE_DB_PATH", str(test_db))
    monkeypatch.setenv("RESUME_ENGINE_UI_STORAGE", str(ui_root))
    monkeypatch.setenv("RESUME_ENGINE_FORCE_TEST_ISOLATION", "1")

    # Soft-assert before any import-side connection
    resolved = Path(os.environ["RESUME_ENGINE_DB_PATH"]).resolve()
    if resolved == PRODUCTION_DB:
        raise RuntimeError(
            "TEST_DATABASE_ISOLATION_VIOLATION: fixture would use production DB"
        )

    # Reset schema for this temp DB so first connect is clean
    from resume_engine.ui.db import ensure_ui_schema

    ensure_ui_schema()

    yield {
        "db_path": test_db,
        "ui_root": ui_root,
        "production_db": PRODUCTION_DB,
    }

    # Post-test: production must still not equal active path
    active = Path(os.environ.get("RESUME_ENGINE_DB_PATH", "")).resolve()
    if active == PRODUCTION_DB:
        raise RuntimeError(
            "TEST_DATABASE_ISOLATION_VIOLATION: test ended on production DB path"
        )


@pytest.fixture
def isolated_storage(_isolate_resume_engine_storage):
    return _isolate_resume_engine_storage
