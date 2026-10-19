import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from ratelab.algorithms.token_bucket import TokenBucketLimiter
from ratelab.clock import FakeClock
from ratelab.limiter import RateLimitDecision, RateLimitRule
from ratelab.store.failure_policy import (
    CircuitBreaker,
    LimiterUnavailableError,
    StoreFailurePolicyLimiter,
)

pytestmark = pytest.mark.anyio

RULE = RateLimitRule(limit=10, window_seconds=1)
ALLOWED = RateLimitDecision(True, 10, 9, 0.1)


class SwitchableStoreLimiter:
    """Stands in for the Redis limiter; raises while ``is_down``."""

    def __init__(self) -> None:
        self.is_down = False
        self.calls = 0

    async def acquire(self, key: str, cost: int = 1) -> RateLimitDecision:
        self.calls += 1
        if self.is_down:
            raise RedisConnectionError("connection refused")
        return ALLOWED


def build_limiter(
    on_store_failure: str, clock: FakeClock
) -> tuple[StoreFailurePolicyLimiter, SwitchableStoreLimiter]:
    store = SwitchableStoreLimiter()
    limiter = StoreFailurePolicyLimiter(
        route_name="items",
        rule=RULE,
        store_limiter=store,
        breaker=CircuitBreaker(failure_threshold=3, open_seconds=2.0, clock=clock),
        on_store_failure=on_store_failure,
        local_limiter=TokenBucketLimiter(RateLimitRule(2, 1), clock),
    )
    return limiter, store


async def test_fail_open_allows_and_breaker_stops_calling_redis() -> None:
    clock = FakeClock(100.0)
    limiter, store = build_limiter("allow", clock)
    store.is_down = True

    decisions = [await limiter.acquire("k") for _ in range(10)]

    assert all(decision.is_allowed for decision in decisions)
    assert store.calls == 3


async def test_fail_closed_raises_unavailable_with_retry_after() -> None:
    limiter, store = build_limiter("reject", FakeClock(100.0))
    store.is_down = True

    with pytest.raises(LimiterUnavailableError) as raised:
        await limiter.acquire("k")

    assert raised.value.retry_after_seconds == 2.0


async def test_local_fallback_counts_in_this_replica() -> None:
    limiter, store = build_limiter("local", FakeClock(100.0))
    store.is_down = True

    decisions = [await limiter.acquire("k") for _ in range(3)]

    assert [decision.is_allowed for decision in decisions] == [True, True, False]


async def test_breaker_tries_redis_again_after_the_open_period() -> None:
    clock = FakeClock(100.0)
    limiter, store = build_limiter("allow", clock)
    store.is_down = True
    for _ in range(5):
        await limiter.acquire("k")
    store.is_down = False

    await limiter.acquire("k")
    assert store.calls == 3

    clock.advance(2.1)
    assert await limiter.acquire("k") == ALLOWED
    assert store.calls == 4


async def test_unknown_failure_action_is_an_error() -> None:
    limiter, store = build_limiter("shrug", FakeClock(100.0))
    store.is_down = True

    with pytest.raises(ValueError, match="shrug"):
        await limiter.acquire("k")
