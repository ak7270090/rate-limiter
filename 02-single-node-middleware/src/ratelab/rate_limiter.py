"""The interface every limiter implements, and the shared in-memory base class."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Generic, Protocol

from ratelab.clock import Clock, SystemClock
from ratelab.constants import RETRY_MARGIN_SECONDS
from ratelab.key_state_store import KeyStateStore, StateT


@dataclass(frozen=True)
class RateLimitRule:
    """``limit`` requests per ``window_seconds``; ``burst`` sets the bucket capacity if given."""

    limit: int
    window_seconds: float
    burst: int | None = None

    @property
    def capacity(self) -> int:
        return self.burst if self.burst is not None else self.limit

    @property
    def rate_per_second(self) -> float:
        return self.limit / self.window_seconds


@dataclass(frozen=True)
class RateLimitDecision:
    """The answer to one ``acquire`` call."""

    is_allowed: bool
    limit: int
    remaining: int
    reset_after_seconds: float
    retry_after_seconds: float | None = None
    delay_seconds: float = 0.0


class RateLimiter(Protocol):
    """Decide whether ``key`` may spend ``cost`` units now."""

    async def acquire(self, key: str, cost: int = 1) -> RateLimitDecision: ...


def build_decision(
    *,
    is_allowed: bool,
    limit: int,
    remaining: float,
    reset_after_seconds: float,
    retry_after_seconds: float = 0.0,
    delay_seconds: float = 0.0,
) -> RateLimitDecision:
    """Clamp and round the raw numbers an algorithm computed."""
    return RateLimitDecision(
        is_allowed=is_allowed,
        limit=limit,
        remaining=max(int(remaining), 0),
        reset_after_seconds=max(reset_after_seconds, 0.0),
        retry_after_seconds=None
        if is_allowed
        else max(retry_after_seconds, 0.0) + RETRY_MARGIN_SECONDS,
        delay_seconds=delay_seconds,
    )


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
        if not 1 <= cost <= self.rule.capacity:
            raise ValueError(f"cost {cost} must be between 1 and {self.rule.capacity}")
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
