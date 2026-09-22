from resume_engine.learning.strategy_memory import save_strategy_memory_summary


def update_learning_patterns() -> dict:
    path = save_strategy_memory_summary()
    return {
        "updated": True,
        "strategy_memory_summary": str(path),
    }
