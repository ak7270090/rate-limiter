import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from ratelab.clock import FakeClock
from ratelab.limiter import RateLimitDecision
from ratelab.storage.failure_policy import (
    CircuitBreaker,
    LimiterUnavailableError,
    StoreFailurePolicyLimiter,
)

pytestmark = pytest.mark.anyio

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
        fail_open_limit=10,
        store_limiter=store,
        breaker=CircuitBreaker(failure_threshold=3, open_seconds=2.0, clock=clock),
        on_store_failure=on_store_failure,
    )
    return limiter, store


async def test_fail_open_allows_and_breaker_stops_calling_redis() -> None:
    limiter, store = build_limiter("allow", FakeClock(100.0))
    store.is_down = True

    decisions = [await limiter.acquire("k") for _ in range(10)]

    assert all(decision.is_allowed for decision in decisions)
    assert decisions[0].remaining == 10
    assert store.calls == 3


async def test_fail_closed_raises_unavailable_with_retry_after() -> None:
    limiter, store = build_limiter("reject", FakeClock(100.0))
    store.is_down = True

    with pytest.raises(LimiterUnavailableError) as raised:
        await limiter.acquire("k")

    assert raised.value.retry_after_seconds == 2.0


async def test_breaker_tries_redis_again_after_the_open_period() -> None:
    clock = FakeClock(100.0)
    limiter, store = build_limiter("allow", clock)
    store.is_down = True
    for _ in range(5):
        await limiter.acquire("k")
    store.is_down = False

    clock.advance(2.1)

    assert await limiter.acquire("k") == ALLOWED
    assert store.calls == 4


async def test_any_store_fault_follows_the_policy() -> None:
    limiter, store = build_limiter("allow", FakeClock(100.0))

    async def raise_client_bug(key: str, cost: int = 1) -> RateLimitDecision:
        raise RuntimeError("unable to perform operation on <TCPTransport closed=True>")

    store.acquire = raise_client_bug

    assert (await limiter.acquire("k")).is_allowed


async def test_unknown_failure_action_is_rejected_at_construction() -> None:
    with pytest.raises(ValueError, match="local"):
        build_limiter("local", FakeClock(100.0))
