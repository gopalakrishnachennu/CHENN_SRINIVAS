"""Phase 3.1+ UI SQLite schema (shared DB). Product model: candidates, jobs, families, matches."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from resume_engine.config.settings import assert_db_path_not_production, ensure_storage_dirs

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

CREATE TABLE IF NOT EXISTS family_registry (
    family_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    aliases_json TEXT NOT NULL DEFAULT '[]',
    compatible_json TEXT NOT NULL DEFAULT '[]',
    hybrid_json TEXT NOT NULL DEFAULT '[]',
    blocked_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'active',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jd_library (
    id TEXT PRIMARY KEY,
    jd_hash TEXT,
    title TEXT,
    company TEXT,
    location TEXT,
    job_url TEXT,
    source TEXT,
    seniority TEXT,
    primary_family TEXT,
    secondary_family TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    blueprint_path TEXT,
    jd_text TEXT,
    metadata_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS resume_runs (
    run_id TEXT PRIMARY KEY,
    candidate_id TEXT,
    jd_id TEXT,
    jd_hash TEXT,
    job_id TEXT,
    status TEXT,
    match_type TEXT,
    summary_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS match_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    match_type TEXT NOT NULL,
    score REAL,
    details_json TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(candidate_id, job_id)
);

CREATE TABLE IF NOT EXISTS resume_library (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'generating',
    provenance TEXT NOT NULL DEFAULT 'GENERATED_ROLE_POSITIONING',
    run_id TEXT,
    variant_index INTEGER,
    score REAL,
    result_path TEXT,
    payload_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_ui_jobs_status ON ui_jobs(status);
CREATE INDEX IF NOT EXISTS idx_blueprint_versions_hash ON blueprint_versions(jd_hash);
CREATE INDEX IF NOT EXISTS idx_jd_library_family ON jd_library(primary_family);
CREATE INDEX IF NOT EXISTS idx_jd_library_status ON jd_library(status);
CREATE INDEX IF NOT EXISTS idx_resume_runs_candidate ON resume_runs(candidate_id);
CREATE INDEX IF NOT EXISTS idx_match_cache_cand ON match_cache(candidate_id);
CREATE INDEX IF NOT EXISTS idx_match_cache_job ON match_cache(job_id);
CREATE INDEX IF NOT EXISTS idx_resume_lib_cand ON resume_library(candidate_id);
CREATE INDEX IF NOT EXISTS idx_resume_lib_job ON resume_library(job_id);
"""

# Columns added defensively after CREATE IF NOT EXISTS (SQLite ALTER)
_UI_SCHEMA_ALTERS = [
    "ALTER TABLE jd_library ADD COLUMN analysis_status TEXT DEFAULT 'NEEDS_ANALYSIS'",
    "ALTER TABLE jd_library ADD COLUMN analysis_version INTEGER DEFAULT 0",
    "ALTER TABLE jd_library ADD COLUMN jd_content_hash TEXT",
    "ALTER TABLE candidate_profiles ADD COLUMN version INTEGER DEFAULT 1",
    "ALTER TABLE match_cache ADD COLUMN candidate_version INTEGER DEFAULT 0",
    "ALTER TABLE match_cache ADD COLUMN job_analysis_version INTEGER DEFAULT 0",
    "ALTER TABLE match_cache ADD COLUMN family_registry_version TEXT",
]

_UI_SCHEMA_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_jd_library_content_hash ON jd_library(jd_content_hash)",
    "CREATE INDEX IF NOT EXISTS idx_jd_library_job_url ON jd_library(job_url)",
    "CREATE INDEX IF NOT EXISTS idx_jd_library_analysis ON jd_library(analysis_status)",
]

# Engine family_id → display. Matching uses family_id; UI shows display_name.
DEFAULT_FAMILIES: list[dict] = [
    {
        "family_id": "ai_ml",
        "display_name": "AI / ML",
        "aliases": ["AI", "ML", "GenAI", "Machine Learning"],
        "compatible": ["data_engineering", "data_analytics", "software_engineering"],
        "hybrid": ["data_engineering", "devops_cloud"],
        "blocked": ["finance_analytics", "salesforce", "manufacturing_test"],
    },
    {
        "family_id": "data_engineering",
        "display_name": "Data Engineering",
        "aliases": ["DE", "Data Platform"],
        "compatible": ["ai_ml", "data_analytics", "software_engineering"],
        "hybrid": ["ai_ml", "devops_cloud"],
        "blocked": ["salesforce", "marketing_analytics"],
    },
    {
        "family_id": "data_analytics",
        "display_name": "Data Analytics",
        "aliases": ["Analytics", "BI"],
        "compatible": ["data_engineering", "ai_ml", "finance_analytics", "marketing_analytics"],
        "hybrid": ["data_engineering"],
        "blocked": ["cybersecurity", "manufacturing_test"],
    },
    {
        "family_id": "devops_cloud",
        "display_name": "DevOps / Cloud",
        "aliases": ["Cloud", "SRE", "Platform"],
        "compatible": ["software_engineering", "infrastructure_support", "cybersecurity"],
        "hybrid": ["ai_ml", "data_engineering"],
        "blocked": ["finance_analytics", "salesforce", "marketing_analytics"],
    },
    {
        "family_id": "software_engineering",
        "display_name": "Software Engineering",
        "aliases": ["Backend", "Full Stack", "SWE"],
        "compatible": ["ai_ml", "data_engineering", "devops_cloud", "test_engineering"],
        "hybrid": ["devops_cloud", "ai_ml"],
        "blocked": ["manufacturing_test", "finance_analytics"],
    },
    {
        "family_id": "test_engineering",
        "display_name": "Testing / QA",
        "aliases": ["QA", "SDET", "Test"],
        "compatible": ["software_engineering", "manufacturing_test"],
        "hybrid": ["software_engineering"],
        "blocked": ["finance_analytics", "salesforce", "marketing_analytics"],
    },
    {
        "family_id": "infrastructure_support",
        "display_name": "Infrastructure Support",
        "aliases": ["IT Support", "SysAdmin"],
        "compatible": ["devops_cloud", "cybersecurity"],
        "hybrid": ["devops_cloud"],
        "blocked": ["ai_ml", "finance_analytics", "salesforce"],
    },
    {
        "family_id": "cybersecurity",
        "display_name": "Cybersecurity",
        "aliases": ["Security", "InfoSec"],
        "compatible": ["devops_cloud", "infrastructure_support", "software_engineering"],
        "hybrid": ["devops_cloud"],
        "blocked": ["marketing_analytics", "salesforce", "manufacturing_test"],
    },
    {
        "family_id": "salesforce",
        "display_name": "Salesforce",
        "aliases": ["SFDC", "CRM"],
        "compatible": ["software_engineering"],
        "hybrid": [],
        "blocked": ["ai_ml", "data_engineering", "cybersecurity", "manufacturing_test"],
    },
    {
        "family_id": "finance_analytics",
        "display_name": "Finance Analytics",
        "aliases": ["FinAnalytics", "FP&A Analytics"],
        "compatible": ["data_analytics"],
        "hybrid": ["data_analytics"],
        "blocked": ["ai_ml", "devops_cloud", "cybersecurity", "salesforce"],
    },
    {
        "family_id": "marketing_analytics",
        "display_name": "Marketing Analytics",
        "aliases": ["Growth Analytics"],
        "compatible": ["data_analytics"],
        "hybrid": ["data_analytics"],
        "blocked": ["cybersecurity", "devops_cloud", "manufacturing_test"],
    },
    {
        "family_id": "manufacturing_test",
        "display_name": "Manufacturing Test",
        "aliases": ["Hardware Test", "ATE"],
        "compatible": ["test_engineering"],
        "hybrid": ["test_engineering"],
        "blocked": ["ai_ml", "salesforce", "finance_analytics", "marketing_analytics"],
    },
]


def ui_db_path() -> Path:
    ensure_storage_dirs()
    return assert_db_path_not_production(context="ui_db_path")


def connect_ui_db() -> sqlite3.Connection:
    import os

    from resume_engine.config.settings import production_sqlite_db_path

    path = ui_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if (
        os.getenv("PYTEST_CURRENT_TEST") or os.getenv("RESUME_ENGINE_FORCE_TEST_ISOLATION")
    ) and path.resolve() == production_sqlite_db_path():
        raise RuntimeError(
            "TEST_DATABASE_ISOLATION_VIOLATION: connect_ui_db refused production DB"
        )
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def seed_family_registry(conn: sqlite3.Connection) -> None:
    import json
    from datetime import UTC, datetime

    now = datetime.now(UTC).isoformat()
    for fam in DEFAULT_FAMILIES:
        existing = conn.execute(
            "SELECT family_id FROM family_registry WHERE family_id = ?",
            (fam["family_id"],),
        ).fetchone()
        if existing:
            continue
        conn.execute(
            """
            INSERT INTO family_registry(
              family_id, display_name, aliases_json, compatible_json,
              hybrid_json, blocked_json, status, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'active', ?)
            """,
            (
                fam["family_id"],
                fam["display_name"],
                json.dumps(fam["aliases"]),
                json.dumps(fam["compatible"]),
                json.dumps(fam["hybrid"]),
                json.dumps(fam["blocked"]),
                now,
            ),
        )


def ensure_ui_schema(conn: sqlite3.Connection | None = None) -> None:
    owned = conn is None
    if owned:
        conn = connect_ui_db()
    try:
        conn.executescript(UI_SCHEMA)
        for stmt in _UI_SCHEMA_ALTERS:
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass  # column already exists
        for stmt in _UI_SCHEMA_INDEXES:
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass
        seed_family_registry(conn)
        conn.commit()
    finally:
        if owned:
            conn.close()
