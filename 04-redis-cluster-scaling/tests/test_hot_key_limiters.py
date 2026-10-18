import asyncio
import random

import pytest

from ratelab.clock import FakeClock
from ratelab.hot_key_limiters import SplitKeyLimiter, TokenLeaseLimiter, split_rule
from ratelab.policy_registry import RoutePolicy
from ratelab.rate_limiter import RateLimitDecision, RateLimitRule
from ratelab.redis_failure_policy import CircuitBreaker
from ratelab.route_limiters import RouteLimiterFactory
from ratelab.token_bucket import TokenBucketLimiter

pytestmark = pytest.mark.anyio


class CountingStoreLimiter:
    """Stands in for the Redis limiter: a token bucket that records every call."""

    def __init__(self, rule: RateLimitRule, clock: FakeClock) -> None:
        self._bucket = TokenBucketLimiter(rule, clock)
        self.calls: list[tuple[str, int]] = []

    async def acquire(self, key: str, cost: int = 1) -> RateLimitDecision:
        await asyncio.sleep(0)
        self.calls.append((key, cost))
        return self._bucket.try_acquire(key, cost)


async def test_split_sends_each_request_to_a_random_sub_key() -> None:
    random.seed(7)
    store = CountingStoreLimiter(RateLimitRule(10, 10), FakeClock(100.0))
    limiter = SplitKeyLimiter(store, split_count=4)

    for _ in range(20):
        await limiter.acquire("search:all")

    assert {key for key, _ in store.calls} == {f"search:all#{index}" for index in range(4)}


async def test_split_rule_divides_limit_and_burst() -> None:
    assert split_rule(RateLimitRule(300, 10, burst=50), 10) == RateLimitRule(30, 10, burst=5)
    assert split_rule(RateLimitRule(5, 10), 10) == RateLimitRule(1, 10)


async def test_lease_takes_tokens_in_batches_and_spends_them_locally() -> None:
    clock = FakeClock(100.0)
    store = CountingStoreLimiter(RateLimitRule(100, 10), clock)
    limiter = TokenLeaseLimiter(store, lease_size=30, lease_ttl_seconds=1.0, clock=clock)

    decisions = await asyncio.gather(*(limiter.acquire("search:all") for _ in range(50)))

    assert all(decision.is_allowed for decision in decisions)
    assert store.calls == [("search:all", 30), ("search:all", 30)]


async def test_expired_lease_is_dropped_and_a_new_one_taken() -> None:
    clock = FakeClock(100.0)
    store = CountingStoreLimiter(RateLimitRule(100, 10), clock)
    limiter = TokenLeaseLimiter(store, lease_size=30, lease_ttl_seconds=1.0, clock=clock)
    await limiter.acquire("k")

    clock.advance(1.5)
    await limiter.acquire("k")

    assert len(store.calls) == 2


async def test_rejected_lease_falls_back_to_single_tokens() -> None:
    clock = FakeClock(100.0)
    store = CountingStoreLimiter(RateLimitRule(40, 10), clock)
    limiter = TokenLeaseLimiter(store, lease_size=30, lease_ttl_seconds=1.0, clock=clock)

    decisions = [await limiter.acquire("k") for _ in range(45)]

    assert sum(decision.is_allowed for decision in decisions) == 40
    assert store.calls[:2] == [("k", 30), ("k", 30)]
    assert ("k", 1) in store.calls
    # 1 lease, 10 x (lease + single) for the last tokens, 1 x (lease + single) rejected; the
    # remaining 4 requests are rejected without calling Redis
    assert len(store.calls) == 23
    assert decisions[-1].retry_after_seconds == pytest.approx(0.25, abs=0.01)


async def test_local_rejection_ends_at_the_retry_after_time() -> None:
    clock = FakeClock(100.0)
    store = CountingStoreLimiter(RateLimitRule(10, 1), clock)
    limiter = TokenLeaseLimiter(store, lease_size=10, lease_ttl_seconds=1.0, clock=clock)
    for _ in range(11):
        await limiter.acquire("k")
    calls_while_blocked = len(store.calls)

    assert not (await limiter.acquire("k")).is_allowed
    assert len(store.calls) == calls_while_blocked

    clock.advance(0.2)
    assert (await limiter.acquire("k")).is_allowed


async def test_factory_builds_the_strategy_from_the_policy() -> None:
    factory = RouteLimiterFactory(
        redis=None,
        scripts={"sliding_window_counter": None},
        breaker=CircuitBreaker(3, 2.0),
        replica_count_for_local_fallback=3,
    )
    base = {
        "name": "search",
        "method": "GET",
        "path": "/search",
        "algorithm": "sliding_window_counter",
        "limit": 300,
        "window_seconds": 10,
    }

    split = factory.create_store_limiter(RoutePolicy(**base, hot_key_strategy="split"))
    lease = factory.create_store_limiter(
        RoutePolicy(**base, hot_key_strategy="lease", lease_size=500)
    )

    assert isinstance(split, SplitKeyLimiter)
    assert isinstance(lease, TokenLeaseLimiter)
    assert lease._lease_size == 300
