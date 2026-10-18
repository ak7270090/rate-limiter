"""The limiter interface and the decision it returns."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RateLimitRule:
    """``limit`` requests per ``window_seconds``; ``burst`` sets the capacity if given."""

    limit: int
    window_seconds: float
    burst: int | None = None

    @property
    def capacity(self) -> int:
        return self.burst if self.burst is not None else self.limit


@dataclass(frozen=True)
class TierState:
    """Where one tier stands after a decision."""

    name: str
    limit: int
    window_seconds: float
    remaining: int
    reset_after_seconds: float


@dataclass(frozen=True)
class RateLimitDecision:
    """The answer to one ``acquire`` call, with every tier's state."""

    is_allowed: bool
    limit: int
    remaining: int
    reset_after_seconds: float
    retry_after_seconds: float | None = None
    tier_states: tuple[TierState, ...] = ()
    rejected_by: str | None = None


class RateLimiter(Protocol):
    """Decide whether ``key`` may spend ``cost`` units now."""

    async def acquire(self, key: str, cost: int = 1) -> RateLimitDecision: ...


def ensure_cost_fits(cost: int, rule: RateLimitRule) -> None:
    """A request costing more than the capacity could never be allowed."""
    if not 1 <= cost <= rule.capacity:
        raise ValueError(f"cost {cost} must be between 1 and {rule.capacity}")
