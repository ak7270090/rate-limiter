"""Look up a limiter class by its algorithm name."""

from ratelab.algorithms.fixed_window import FixedWindowLimiter
from ratelab.algorithms.gcra import GcraLimiter
from ratelab.algorithms.in_memory import InMemoryLimiter
from ratelab.algorithms.leaky_bucket import LeakyBucketLimiter, LeakyBucketQueueLimiter
from ratelab.algorithms.sliding_window_counter import SlidingWindowCounterLimiter
from ratelab.algorithms.sliding_window_log import SlidingWindowLogLimiter
from ratelab.algorithms.token_bucket import TokenBucketLimiter
from ratelab.clock import Clock
from ratelab.constants import (
    ALGORITHM_FIXED_WINDOW,
    ALGORITHM_GCRA,
    ALGORITHM_LEAKY_BUCKET,
    ALGORITHM_LEAKY_BUCKET_QUEUE,
    ALGORITHM_SLIDING_WINDOW_COUNTER,
    ALGORITHM_SLIDING_WINDOW_LOG,
    ALGORITHM_TOKEN_BUCKET,
)
from ratelab.limiter import RateLimitRule

IN_MEMORY_LIMITERS: dict[str, type[InMemoryLimiter]] = {
    ALGORITHM_FIXED_WINDOW: FixedWindowLimiter,
    ALGORITHM_SLIDING_WINDOW_LOG: SlidingWindowLogLimiter,
    ALGORITHM_SLIDING_WINDOW_COUNTER: SlidingWindowCounterLimiter,
    ALGORITHM_TOKEN_BUCKET: TokenBucketLimiter,
    ALGORITHM_LEAKY_BUCKET: LeakyBucketLimiter,
    ALGORITHM_LEAKY_BUCKET_QUEUE: LeakyBucketQueueLimiter,
    ALGORITHM_GCRA: GcraLimiter,
}


def create_in_memory_limiter(
    algorithm: str, rule: RateLimitRule, clock: Clock | None = None
) -> InMemoryLimiter:
    """Create the limiter for ``algorithm``; raises ``KeyError`` for an unknown name."""
    return IN_MEMORY_LIMITERS[algorithm](rule, clock)
