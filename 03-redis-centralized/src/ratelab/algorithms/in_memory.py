"""The shared base class of the in-memory algorithms: per-key state kept in a dict."""

from abc import ABC, abstractmethod
from typing import Generic

from ratelab.algorithms.state_store import KeyStateStore, StateT
from ratelab.clock import Clock, SystemClock
from ratelab.limiter import RateLimitDecision, RateLimitRule, ensure_cost_fits


class InMemoryLimiter(ABC, Generic[StateT]):
    """Holds per-key state in a dict.

    ``try_acquire`` never awaits, so on one asyncio event loop a read-decide-write cannot be
    interleaved with another request and no lock is needed.
    """

    def __init__(self, rule: RateLimitRule, clock: Clock | None = None) -> None:
        self.rule = rule
        self.clock = clock or SystemClock()
        self._store: KeyStateStore[StateT] = KeyStateStore()

    async def acquire(self, key: str, cost: int = 1) -> RateLimitDecision:
        return self.try_acquire(key, cost)

    def try_acquire(self, key: str, cost: int = 1) -> RateLimitDecision:
        ensure_cost_fits(cost, self.rule)
        now = self.clock.now()
        decision, new_state = self.decide(self._store.get(key, now), now, cost)
        self._store.put(key, new_state, now + decision.reset_after_seconds, now)
        return decision

    @property
    def tracked_key_count(self) -> int:
        return len(self._store)

    @abstractmethod
    def decide(
        self, state: StateT | None, now: float, cost: int
    ) -> tuple[RateLimitDecision, StateT]:
        """Return the decision and the key's new state; ``state`` is ``None`` for a fresh key."""
