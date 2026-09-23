"""LearningRepository — SQLite primary + optional JSONL dual-write (Wave 4)."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from resume_engine.config.settings import (
    SQLITE_DB_PATH,
    ensure_storage_dirs,
    portable_path,
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    jd_hash TEXT,
    created_at TEXT,
    primary_family TEXT,
    secondary_family TEXT,
    seniority TEXT,
    model TEXT,
    prompt_version TEXT,
    metadata_json TEXT
);

CREATE TABLE IF NOT EXISTS variant_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT,
    run_id TEXT,
    jd_hash TEXT,
    variant_id TEXT,
    variant_positioning TEXT,
    primary_family TEXT,
    secondary_family TEXT,
    hybrid INTEGER,
    seniority TEXT,
    passed INTEGER,
    score_before REAL,
    score_after REAL,
    eligible_for_learning INTEGER,
    payload_json TEXT
);

CREATE TABLE IF NOT EXISTS failures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT,
    run_id TEXT,
    jd_hash TEXT,
    variant_id TEXT,
    failure_codes_json TEXT,
    payload_json TEXT
);

CREATE TABLE IF NOT EXISTS strategy_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT,
    memory_key TEXT,
    average_score REAL,
    sample_count INTEGER,
    payload_json TEXT
);

CREATE TABLE IF NOT EXISTS resume_fingerprints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT,
    jd_hash TEXT,
    run_id TEXT,
    variant_id TEXT,
    passed INTEGER,
    normalized_text_hash TEXT,
    text_preview TEXT,
    payload_json TEXT
);

CREATE TABLE IF NOT EXISTS repair_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT,
    run_id TEXT,
    jd_hash TEXT,
    variant_id TEXT,
    repair_count INTEGER,
    successful_repairs_json TEXT,
    payload_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_outcomes_family
    ON variant_outcomes(primary_family, secondary_family, seniority, passed);
CREATE INDEX IF NOT EXISTS idx_fingerprints_jd
    ON resume_fingerprints(jd_hash, passed);

CREATE TABLE IF NOT EXISTS online_policy_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    jd_hash TEXT,
    variant_id TEXT,
    policy_version TEXT,
    mode TEXT,
    production_action TEXT,
    shadow_top_action TEXT,
    shadow_agrees INTEGER,
    context_json TEXT,
    available_actions_json TEXT,
    prediction_json TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS online_policy_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id INTEGER,
    run_id TEXT,
    jd_hash TEXT,
    variant_id TEXT,
    action TEXT,
    reward REAL,
    reward_components_json TEXT,
    eligible INTEGER,
    policy_version TEXT,
    created_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_online_decisions_run
    ON online_policy_decisions(run_id);
CREATE INDEX IF NOT EXISTS idx_online_decisions_jd
    ON online_policy_decisions(jd_hash);
CREATE INDEX IF NOT EXISTS idx_online_decisions_policy
    ON online_policy_decisions(policy_version);
CREATE INDEX IF NOT EXISTS idx_online_obs_run
    ON online_policy_observations(run_id);
CREATE INDEX IF NOT EXISTS idx_online_obs_jd
    ON online_policy_observations(jd_hash);
CREATE INDEX IF NOT EXISTS idx_online_obs_action
    ON online_policy_observations(action);
CREATE INDEX IF NOT EXISTS idx_online_obs_policy
    ON online_policy_observations(policy_version);
CREATE INDEX IF NOT EXISTS idx_online_obs_eligible
    ON online_policy_observations(eligible);
CREATE INDEX IF NOT EXISTS idx_online_decisions_run_variant
    ON online_policy_decisions(run_id, variant_id);
CREATE INDEX IF NOT EXISTS idx_online_obs_decision
    ON online_policy_observations(decision_id);
"""


class LearningRepository:
    """
    Storage abstraction over SQLite with optional legacy JSONL dual-write.

    Gate 3: SQLite is the sole learning write SoT by default.
    Set dual_write_jsonl=True (or LEARNING_DUAL_WRITE_JSONL=1) for opt-in backup.
    """

    def __init__(
        self,
        db_path: Path | None = None,
        *,
        dual_write_jsonl: bool = False,
    ) -> None:
        ensure_storage_dirs()
        self.db_path = Path(db_path) if db_path else SQLITE_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.dual_write_jsonl = dual_write_jsonl
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA_SQL)
            self._migrate_online_columns(conn)
            conn.commit()

    @staticmethod
    def _migrate_online_columns(conn: sqlite3.Connection) -> None:
        def ensure(table: str, column: str, typedef: str) -> None:
            cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            if column not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {typedef}")

        ensure("online_policy_observations", "reward_schema_version", "TEXT")
        ensure("online_policy_observations", "linkage_status", "TEXT")
        ensure("online_policy_observations", "train_status", "TEXT")
        # Unique applied observation identity — ignore failure if duplicates already exist.
        try:
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_online_obs_unique_final
                ON online_policy_observations(run_id, variant_id, policy_version)
                WHERE train_status = 'APPLIED'
                """
            )
        except sqlite3.OperationalError:
            pass

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    def save_run(self, record: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO runs (
                    run_id, jd_hash, created_at, primary_family, secondary_family,
                    seniority, model, prompt_version, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.get("run_id"),
                    record.get("jd_hash"),
                    record.get("created_at") or self._now(),
                    record.get("primary_family"),
                    record.get("secondary_family"),
                    record.get("seniority"),
                    record.get("model"),
                    record.get("prompt_version"),
                    json.dumps(record, ensure_ascii=False),
                ),
            )
            conn.commit()

    def save_outcome(self, record: dict[str, Any]) -> Path:
        enriched = {"created_at": self._now(), **record}
        if self.dual_write_jsonl:
            from resume_engine.learning.outcome_store import OUTCOMES_FILE

            OUTCOMES_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(OUTCOMES_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(enriched, ensure_ascii=False) + "\n")

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO variant_outcomes (
                    created_at, run_id, jd_hash, variant_id, variant_positioning,
                    primary_family, secondary_family, hybrid, seniority, passed,
                    score_before, score_after, eligible_for_learning, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    enriched.get("created_at"),
                    enriched.get("run_id"),
                    enriched.get("jd_hash"),
                    enriched.get("variant_id"),
                    enriched.get("variant_positioning"),
                    enriched.get("primary_family"),
                    enriched.get("secondary_family"),
                    1 if enriched.get("hybrid") else 0,
                    enriched.get("seniority"),
                    1 if enriched.get("passed") or enriched.get("successful_pattern") else 0,
                    enriched.get("score_before", enriched.get("score_before_repair")),
                    enriched.get("score_after", enriched.get("score_after_repair")),
                    1 if enriched.get("eligible_for_learning") else 0,
                    json.dumps(enriched, ensure_ascii=False),
                ),
            )
            repair_count = int(enriched.get("repair_count") or 0)
            if repair_count > 0 or enriched.get("successful_repairs"):
                conn.execute(
                    """
                    INSERT INTO repair_events (
                        created_at, run_id, jd_hash, variant_id, repair_count,
                        successful_repairs_json, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        enriched.get("created_at"),
                        enriched.get("run_id"),
                        enriched.get("jd_hash"),
                        enriched.get("variant_id"),
                        repair_count,
                        json.dumps(enriched.get("successful_repairs") or [], ensure_ascii=False),
                        json.dumps(
                            {
                                "repairs": enriched.get("repairs"),
                                "score_before": enriched.get("score_before"),
                                "score_after": enriched.get("score_after"),
                            },
                            ensure_ascii=False,
                        ),
                    ),
                )
            conn.commit()
        return self.db_path

    def save_failure(self, record: dict[str, Any]) -> Path:
        enriched = {"created_at": self._now(), **record}
        if self.dual_write_jsonl:
            from resume_engine.learning.failure_store import FAILURES_FILE

            FAILURES_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(FAILURES_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(enriched, ensure_ascii=False) + "\n")

        codes = enriched.get("failure_codes") or enriched.get("failures") or []
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO failures (
                    created_at, run_id, jd_hash, variant_id, failure_codes_json, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    enriched.get("created_at"),
                    enriched.get("run_id"),
                    enriched.get("jd_hash"),
                    enriched.get("variant_id"),
                    json.dumps(codes, ensure_ascii=False),
                    json.dumps(enriched, ensure_ascii=False),
                ),
            )
            conn.commit()
        return self.db_path

    def save_fingerprint(self, record: dict[str, Any]) -> Path:
        enriched = {"created_at": self._now(), **record}
        if self.dual_write_jsonl:
            from resume_engine.learning.fingerprint_store import FINGERPRINTS_FILE

            FINGERPRINTS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(FINGERPRINTS_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(enriched, ensure_ascii=False) + "\n")

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO resume_fingerprints (
                    created_at, jd_hash, run_id, variant_id, passed,
                    normalized_text_hash, text_preview, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    enriched.get("created_at"),
                    enriched.get("jd_hash"),
                    enriched.get("run_id"),
                    enriched.get("variant_id"),
                    1 if enriched.get("passed") else 0,
                    enriched.get("normalized_text_hash"),
                    enriched.get("text_preview"),
                    json.dumps(enriched, ensure_ascii=False),
                ),
            )
            conn.commit()
        return self.db_path

    def get_strategy_history(
        self,
        *,
        primary_family: str | None = None,
        secondary_family: str | None = None,
        seniority: str | None = None,
        eligible_only: bool = True,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        clauses = ["1=1"]
        params: list[Any] = []
        if primary_family is not None:
            clauses.append("primary_family = ?")
            params.append(primary_family)
        if secondary_family is not None:
            clauses.append("secondary_family = ?")
            params.append(secondary_family)
        if seniority is not None:
            clauses.append("seniority = ?")
            params.append(seniority)
        if eligible_only:
            clauses.append("eligible_for_learning = 1")
            clauses.append("passed = 1")
        params.append(limit)
        sql = f"""
            SELECT payload_json FROM variant_outcomes
            WHERE {' AND '.join(clauses)}
            ORDER BY id DESC
            LIMIT ?
        """
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def get_prior_variants(
        self,
        jd_hash: str,
        *,
        exclude_run_id: str | None = None,
        passed_only: bool = True,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        clauses = ["jd_hash = ?"]
        params: list[Any] = [jd_hash]
        if passed_only:
            clauses.append("passed = 1")
        if exclude_run_id:
            clauses.append("run_id != ?")
            params.append(exclude_run_id)
        params.append(limit)
        sql = f"""
            SELECT payload_json FROM resume_fingerprints
            WHERE {' AND '.join(clauses)}
            ORDER BY id DESC
            LIMIT ?
        """
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def save_strategy_memory_snapshot(self, summary: dict[str, Any]) -> None:
        created = self._now()
        with self._connect() as conn:
            for key, stats in summary.items():
                if not isinstance(stats, dict):
                    continue
                conn.execute(
                    """
                    INSERT INTO strategy_memory (
                        created_at, memory_key, average_score, sample_count, payload_json
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        created,
                        str(key),
                        float(stats.get("average_score") or 0.0),
                        int(stats.get("count") or 0),
                        json.dumps(stats, ensure_ascii=False),
                    ),
                )
            conn.commit()

    def save_online_decision(self, decision: dict[str, Any]) -> int:
        created = decision.get("created_at") or self._now()
        ranked = decision.get("shadow_ranked_actions") or []
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO online_policy_decisions (
                    run_id, jd_hash, variant_id, policy_version, mode,
                    production_action, shadow_top_action, shadow_agrees,
                    context_json, available_actions_json, prediction_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision.get("run_id"),
                    decision.get("jd_hash"),
                    decision.get("variant_id"),
                    decision.get("policy_version"),
                    decision.get("mode"),
                    decision.get("production_action"),
                    decision.get("shadow_top_action"),
                    1 if decision.get("shadow_agrees_with_production") else 0,
                    json.dumps(decision.get("context") or {}, ensure_ascii=False),
                    json.dumps(decision.get("available_actions") or [], ensure_ascii=False),
                    json.dumps(
                        {
                            "ranked": ranked,
                            "production_order": decision.get("production_order") or [],
                            "production_rank": decision.get("production_rank"),
                            "shadow_rank_of_production_action": decision.get(
                                "shadow_rank_of_production_action"
                            ),
                            "observation_count_at_prediction": decision.get(
                                "observation_count_at_prediction"
                            ),
                            "fallback_reason": decision.get("fallback_reason"),
                        },
                        ensure_ascii=False,
                    ),
                    created,
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def get_online_decision(
        self,
        *,
        run_id: str,
        variant_id: str,
        policy_version: str | None = None,
    ) -> dict[str, Any] | None:
        clauses = ["run_id = ?", "variant_id = ?"]
        params: list[Any] = [run_id, variant_id]
        if policy_version:
            clauses.append("policy_version = ?")
            params.append(policy_version)
        sql = f"""
            SELECT * FROM online_policy_decisions
            WHERE {' AND '.join(clauses)}
            ORDER BY id DESC LIMIT 1
        """
        with self._connect() as conn:
            row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    def has_applied_online_observation(
        self,
        *,
        run_id: str,
        variant_id: str,
        policy_version: str,
    ) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM online_policy_observations
                WHERE run_id = ? AND variant_id = ? AND policy_version = ?
                  AND train_status = 'APPLIED'
                LIMIT 1
                """,
                (run_id, variant_id, policy_version),
            ).fetchone()
        return row is not None

    def save_online_observation(self, observation: dict[str, Any]) -> int:
        created = observation.get("created_at") or self._now()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO online_policy_observations (
                    decision_id, run_id, jd_hash, variant_id, action, reward,
                    reward_components_json, eligible, policy_version, created_at,
                    reward_schema_version, linkage_status, train_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    observation.get("decision_id"),
                    observation.get("run_id"),
                    observation.get("jd_hash"),
                    observation.get("variant_id"),
                    observation.get("action"),
                    float(observation.get("reward") or 0.0),
                    json.dumps(observation.get("reward_components") or {}, ensure_ascii=False),
                    1 if observation.get("eligible") else 0,
                    observation.get("policy_version"),
                    created,
                    observation.get("reward_schema_version"),
                    observation.get("linkage_status"),
                    observation.get("train_status") or ("APPLIED" if observation.get("eligible") else "SKIPPED"),
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def list_online_decisions(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM online_policy_decisions
                ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_online_observations(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM online_policy_observations
                ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def db_portable_path(self) -> str | None:
        return portable_path(self.db_path)


_DEFAULT_REPO: LearningRepository | None = None


def get_default_repository() -> LearningRepository:
    """
    Process-wide LearningRepository.

    Gate 3: SQLite is the sole write SoT by default.
    Opt into legacy JSONL dual-write with LEARNING_DUAL_WRITE_JSONL=1.
    """
    global _DEFAULT_REPO
    if _DEFAULT_REPO is None:
        import os

        dual = os.getenv("LEARNING_DUAL_WRITE_JSONL", "").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        _DEFAULT_REPO = LearningRepository(dual_write_jsonl=dual)
    return _DEFAULT_REPO


def reset_default_repository_for_tests(repo: LearningRepository | None = None) -> None:
    """Test helper to swap the process-wide repository."""
    global _DEFAULT_REPO
    _DEFAULT_REPO = repo
