"""River LinUCB adapter — only public policy surface for Phase 2.8."""

from __future__ import annotations

import logging
from typing import Any

from resume_engine.learning.online.config import (
    ONLINE_POLICY_VERSION,
    get_policy_seed,
)
from resume_engine.learning.online.schemas import PolicyPrediction

logger = logging.getLogger(__name__)


class RiverStrategyPolicy:
    """
    Adapter around river.bandit.LinUCBDisjoint.

    Callers must never invent actions: rank_actions asserts subset of eligible.
    """

    def __init__(
        self,
        *,
        seed: int | None = None,
        policy_version: str = ONLINE_POLICY_VERSION,
        model: Any | None = None,
    ) -> None:
        self.policy_version = policy_version
        self.seed = get_policy_seed() if seed is None else seed
        self._model = model
        self._observation_count = 0
        self._action_counts: dict[str, int] = {}
        self._reward_sum = 0.0
        self._reward_count = 0
        if self._model is None:
            self._model = self._new_model()

    def _new_model(self):
        from river.bandit import LinUCBDisjoint

        return LinUCBDisjoint(seed=self.seed)

    @property
    def observation_count(self) -> int:
        return self._observation_count

    @property
    def action_counts(self) -> dict[str, int]:
        return dict(self._action_counts)

    @property
    def reward_mean(self) -> float | None:
        if self._reward_count <= 0:
            return None
        return self._reward_sum / self._reward_count

    def rank_actions(self, context: dict[str, float], actions: list[str]) -> list[PolicyPrediction]:
        if not actions:
            return []
        unique_actions = list(dict.fromkeys(actions))
        assert set(unique_actions).issubset(set(actions))

        scores: list[tuple[str, float]] = []
        for action in unique_actions:
            score = self._score_action(action, context)
            scores.append((action, score))
        scores.sort(key=lambda item: (-item[1], item[0]))

        ranked: list[PolicyPrediction] = []
        for index, (action, score) in enumerate(scores, start=1):
            ranked.append(
                PolicyPrediction(
                    action=action,
                    rank=index,
                    score=float(score),
                    probability=None,
                    policy_version=self.policy_version,
                    model_observation_count=self._observation_count,
                )
            )

        # Hard invariant: cannot invent actions.
        ranked_actions = {item.action for item in ranked}
        if not ranked_actions.issubset(set(unique_actions)):
            raise AssertionError("River policy invented an action outside eligible set")
        return ranked

    def _score_action(self, action: str, context: dict[str, float]) -> float:
        try:
            dist = self._model._bayes_lin_regs[action].predict_one(context, with_dist=True)
            return float(dist.mu + dist.sigma)
        except Exception:  # noqa: BLE001 — cold-start / missing arm
            # Unseen arms get optimistic prior for ranking exploration in shadow only.
            return 1.0

    def observe(self, context: dict[str, float], action: str, reward: float) -> None:
        clamped = max(0.0, min(1.0, float(reward)))
        self._model.update(action, context, clamped)
        self._observation_count += 1
        self._action_counts[action] = self._action_counts.get(action, 0) + 1
        self._reward_sum += clamped
        self._reward_count += 1

    def save(self) -> None:
        from resume_engine.learning.online.policy_store import save_policy

        save_policy(self)

    def load(self) -> None:
        from resume_engine.learning.online.policy_store import load_policy

        loaded = load_policy()
        if loaded is None:
            return
        self._model = loaded._model
        self._observation_count = loaded._observation_count
        self._action_counts = dict(loaded._action_counts)
        self._reward_sum = loaded._reward_sum
        self._reward_count = loaded._reward_count
        self.policy_version = loaded.policy_version
        self.seed = loaded.seed

    def reset_for_tests(self) -> None:
        self._model = self._new_model()
        self._observation_count = 0
        self._action_counts = {}
        self._reward_sum = 0.0
        self._reward_count = 0


_POLICY_SINGLETON: RiverStrategyPolicy | None = None


def get_default_policy(*, force_new: bool = False) -> RiverStrategyPolicy:
    global _POLICY_SINGLETON
    if force_new or _POLICY_SINGLETON is None:
        policy = RiverStrategyPolicy()
        try:
            policy.load()
        except Exception as exc:  # noqa: BLE001
            logger.warning("ONLINE_POLICY_FALLBACK: load failed: %s", type(exc).__name__)
            policy = RiverStrategyPolicy()
        _POLICY_SINGLETON = policy
    return _POLICY_SINGLETON


def reset_default_policy_for_tests() -> None:
    global _POLICY_SINGLETON
    _POLICY_SINGLETON = None
