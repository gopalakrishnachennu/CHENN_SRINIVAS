import json
from datetime import datetime, timezone
from pathlib import Path

from resume_engine.config.settings import LEARNING_STORAGE_DIR, ensure_storage_dirs


OUTCOMES_FILE = LEARNING_STORAGE_DIR / "outcomes.jsonl"


def save_learning_outcome(record: dict) -> Path:
    ensure_storage_dirs()
    enriched = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        **record,
    }
    with open(OUTCOMES_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(enriched, ensure_ascii=False) + "\n")
    return OUTCOMES_FILE
