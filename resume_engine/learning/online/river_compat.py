"""River LinUCB compatibility boundary (Gate 1.1).

River 0.26.1 LinUCBDisjoint exposes pull/update/ranking publicly but does not
expose per-arm UCB scores for deterministic full ranking. Scoring therefore
uses an isolated private-field adapter. All private access stays here.
"""

from __future__ import annotations

import logging
from typing import Any

import river

logger = logging.getLogger(__name__)

SUPPORTED_RIVER_VERSION = "0.26.1"


def river_version_supported() -> bool:
    return getattr(river, "__version__", None) == SUPPORTED_RIVER_VERSION


def assert_or_warn_river_version() -> bool:
    if river_version_supported():
        return True
    logger.warning(
        "ONLINE_POLICY_FALLBACK: unsupported river version %s (need %s)",
        getattr(river, "__version__", None),
        SUPPORTED_RIVER_VERSION,
    )
    return False


class RiverLinUCBCompat:
    """
    Isolated access to LinUCBDisjoint arm scores.

    Public River APIs used where possible (`update`, `pull`).
    Per-action ranking scores require BayesianLinearRegression UCB from the
    policy's arm registry — private in 0.26.1 — kept only in this class.
    """

    def __init__(self, model: Any) -> None:
        self._model = model

    def score_action(self, action: str, context: dict[str, float]) -> float:
        try:
            regs = getattr(self._model, "_bayes_lin_regs", None)
            if regs is None:
                raise AttributeError("missing _bayes_lin_regs")
            dist = regs[action].predict_one(context, with_dist=True)
            return float(dist.mu + dist.sigma)
        except Exception:  # noqa: BLE001 — cold-start / API drift
            return 1.0

    def update(self, action: str, context: dict[str, float], reward: float) -> None:
        self._model.update(action, context, reward)
