from pathlib import Path

from resume_engine.config.settings import LEARNING_STORAGE_DIR, ensure_storage_dirs

FAILURES_FILE = LEARNING_STORAGE_DIR / "failures.jsonl"


def save_failure_record(record: dict) -> Path:
    ensure_storage_dirs()
    from resume_engine.learning.repository import get_default_repository

    get_default_repository().save_failure(record)
    return FAILURES_FILE
