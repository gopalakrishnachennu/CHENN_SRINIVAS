"""Phase 3.1 UI SQLite schema (same DB as learning repository)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from resume_engine.config.settings import SQLITE_DB_PATH, ensure_storage_dirs

UI_SCHEMA = """
CREATE TABLE IF NOT EXISTS ui_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    classification TEXT NOT NULL DEFAULT 'SAFE',
    updated_at TEXT NOT NULL,
    updated_by TEXT
);

CREATE TABLE IF NOT EXISTS ui_config_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    actor TEXT,
    reason TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS candidate_profiles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS candidate_profile_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    actor TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(profile_id, version)
);

CREATE TABLE IF NOT EXISTS prompt_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'DRAFT',
    content TEXT NOT NULL,
    actor TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(prompt_id, version)
);

CREATE TABLE IF NOT EXISTS document_templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    is_default INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    timestamp TEXT NOT NULL,
    actor TEXT,
    action TEXT NOT NULL,
    entity_type TEXT,
    entity_id TEXT,
    old_value TEXT,
    new_value TEXT,
    metadata_json TEXT
);

CREATE TABLE IF NOT EXISTS ui_jobs (
    job_id TEXT PRIMARY KEY,
    run_id TEXT,
    status TEXT NOT NULL,
    stage TEXT,
    payload_json TEXT,
    result_json TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS blueprint_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    jd_hash TEXT NOT NULL,
    version INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    actor TEXT,
    note TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(jd_hash, version)
);

CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_ui_jobs_status ON ui_jobs(status);
CREATE INDEX IF NOT EXISTS idx_blueprint_versions_hash ON blueprint_versions(jd_hash);
"""


def ui_db_path() -> Path:
    ensure_storage_dirs()
    return Path(SQLITE_DB_PATH)


def connect_ui_db() -> sqlite3.Connection:
    path = ui_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_ui_schema(conn: sqlite3.Connection | None = None) -> None:
    owned = conn is None
    if owned:
        conn = connect_ui_db()
    try:
        conn.executescript(UI_SCHEMA)
        conn.commit()
    finally:
        if owned:
            conn.close()
