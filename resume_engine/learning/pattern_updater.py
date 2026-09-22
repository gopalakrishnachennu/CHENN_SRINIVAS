from resume_engine.config import thresholds
from resume_engine.config.settings import portable_path
from resume_engine.learning.eligibility import is_record_eligible_for_learning
from resume_engine.learning.strategy_memory import (
    load_outcome_records,
    save_strategy_memory_summary,
)


def update_learning_patterns() -> dict:
    path = save_strategy_memory_summary()
    records = load_outcome_records()
    eligible = [record for record in records if is_record_eligible_for_learning(record)]
    return {
        "updated": True,
        "strategy_memory_summary": portable_path(path),
        "outcome_count": len(records),
        "eligible_count": len(eligible),
        "learning_min_sample_count": thresholds.LEARNING_MIN_SAMPLE_COUNT,
    }
