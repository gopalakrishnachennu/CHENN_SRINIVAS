import json
from datetime import UTC, datetime
from pathlib import Path

from resume_engine.config.settings import LEARNING_STORAGE_DIR, ensure_storage_dirs

OUTCOMES_FILE = LEARNING_STORAGE_DIR / "outcomes.jsonl"


def save_learning_outcome(record: dict) -> Path:
    """Persist outcome to JSONL + SQLite via LearningRepository."""
    ensure_storage_dirs()
    from resume_engine.learning.repository import get_default_repository

    get_default_repository().save_outcome(record)
    return OUTCOMES_FILE


def append_outcome_jsonl_only(record: dict) -> Path:
    """Low-level JSONL append used by tests / migration helpers."""
    ensure_storage_dirs()
    enriched = {
        "created_at": datetime.now(UTC).isoformat(),
        **record,
    }
    with open(OUTCOMES_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(enriched, ensure_ascii=False) + "\n")
    return OUTCOMES_FILE
