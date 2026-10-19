"""The interface every limiter implements and the decision it returns."""

from dataclasses import dataclass
from typing import Protocol

from ratelab.constants import RETRY_MARGIN_SECONDS


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
