import json
from collections import defaultdict
from pathlib import Path

from resume_engine.config.settings import LEARNING_STORAGE_DIR
from resume_engine.learning.outcome_store import OUTCOMES_FILE


def summarize_strategy_memory() -> dict:
    if not OUTCOMES_FILE.exists():
        return {}

    grouped = defaultdict(list)
    with open(OUTCOMES_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                record = json.loads(line)
                key = (
                    record.get("primary_family", "unknown"),
                    record.get("secondary_family", "none"),
                    record.get("variant_positioning", "unknown"),
                )
                grouped[key].append(record.get("score_after_repair", record.get("score_before_repair", 0)))

    summary = {}
    for key, scores in grouped.items():
        summary["|".join(key)] = {
            "average_score": round(sum(scores) / len(scores), 2),
            "count": len(scores),
        }
    return summary


def save_strategy_memory_summary() -> Path:
    LEARNING_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    path = LEARNING_STORAGE_DIR / "strategy_memory_summary.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summarize_strategy_memory(), f, indent=2, ensure_ascii=False)
    return path
