"""Leaky bucket, two ways: a meter that rejects overflow, and a queue that delays requests."""

from dataclasses import dataclass

from ratelab.constants import FLOAT_TOLERANCE
from ratelab.rate_limiter import InMemoryLimiter, RateLimitDecision, build_decision


@dataclass(frozen=True, slots=True)
class LeakyBucketState:
    level: float
    updated_at: float


class LeakyBucketLimiter(InMemoryLimiter[LeakyBucketState]):
    """Meter variant: each request adds to the level, which drains at ``limit / window``."""

    def decide(
        self, state: LeakyBucketState | None, now: float, cost: int
    ) -> tuple[RateLimitDecision, LeakyBucketState]:
        capacity = self.rule.capacity
        leak_rate = self.rule.rate_per_second
        level = 0.0 if state is None else max(state.level - (now - state.updated_at) * leak_rate, 0)
        is_allowed = level + cost <= capacity + FLOAT_TOLERANCE
        if is_allowed:
            level += cost
        decision = build_decision(
            is_allowed=is_allowed,
            limit=capacity,
            remaining=capacity - level + FLOAT_TOLERANCE,
            reset_after_seconds=level / leak_rate,
            retry_after_seconds=(level + cost - capacity) / leak_rate,
        )
        return decision, LeakyBucketState(level, now)


class LeakyBucketQueueLimiter(InMemoryLimiter[float]):
    """Queue variant: requests leave one per ``window / limit`` seconds; the caller waits
    ``delay_seconds``. Rejects only when ``capacity`` requests are already waiting.

    The state is the time the queue becomes empty again.
    """

    def decide(self, state: float | None, now: float, cost: int) -> tuple[RateLimitDecision, float]:
        capacity = self.rule.capacity
        seconds_per_request = 1 / self.rule.rate_per_second
        scheduled_at = max(state if state is not None else now, now)
        queued_requests = (scheduled_at - now) / seconds_per_request
        is_allowed = queued_requests + cost <= capacity + FLOAT_TOLERANCE
        queue_empty_at = scheduled_at + cost * seconds_per_request if is_allowed else scheduled_at
        decision = build_decision(
            is_allowed=is_allowed,
            limit=capacity,
            remaining=capacity - (queue_empty_at - now) / seconds_per_request + FLOAT_TOLERANCE,
            reset_after_seconds=queue_empty_at - now,
            retry_after_seconds=(queued_requests + cost - capacity) * seconds_per_request,
            delay_seconds=scheduled_at - now if is_allowed else 0.0,
        )
        return decision, queue_empty_at
