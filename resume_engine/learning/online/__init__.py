"""Phase 2.8 online self-learning (River) — shadow mode by default."""

from resume_engine.learning.online.config import (
    get_online_learning_mode,
    online_learning_enabled,
)
from resume_engine.learning.online.river_policy import RiverStrategyPolicy

__all__ = [
    "RiverStrategyPolicy",
    "get_online_learning_mode",
    "online_learning_enabled",
]
