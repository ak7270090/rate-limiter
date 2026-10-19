"""Token bucket: tokens refill at ``limit / window`` per second up to ``capacity``."""

from dataclasses import dataclass

from ratelab.algorithms.in_memory import InMemoryLimiter
from ratelab.constants import FLOAT_TOLERANCE
from ratelab.limiter import RateLimitDecision, build_decision


@dataclass(frozen=True, slots=True)
class TokenBucketState:
    tokens: float
    updated_at: float


class TokenBucketLimiter(InMemoryLimiter[TokenBucketState]):
    """Allows bursts up to the bucket capacity, then the refill rate; refills lazily on access."""

    def decide(
        self, state: TokenBucketState | None, now: float, cost: int
    ) -> tuple[RateLimitDecision, TokenBucketState]:
        capacity = self.rule.capacity
        refill_rate = self.rule.rate_per_second
        if state is None:
            tokens = float(capacity)
        else:
            tokens = min(capacity, state.tokens + (now - state.updated_at) * refill_rate)
        is_allowed = tokens + FLOAT_TOLERANCE >= cost
        if is_allowed:
            tokens = max(tokens - cost, 0.0)
        decision = build_decision(
            is_allowed=is_allowed,
            limit=capacity,
            remaining=tokens + FLOAT_TOLERANCE,
            reset_after_seconds=(capacity - tokens) / refill_rate,
            retry_after_seconds=(cost - tokens) / refill_rate,
        )
        return decision, TokenBucketState(tokens, now)
