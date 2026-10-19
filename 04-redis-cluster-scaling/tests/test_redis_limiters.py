import asyncio
import time

import pytest
from redis.asyncio import Redis

from ratelab.constants import (
    ALGORITHM_FIXED_WINDOW,
    ALGORITHM_FIXED_WINDOW_INCR,
    ALGORITHM_FIXED_WINDOW_NAIVE,
    ALGORITHM_LEAKY_BUCKET_QUEUE,
    ALGORITHM_SLIDING_WINDOW_COUNTER,
    ALGORITHM_TOKEN_BUCKET,
)
from ratelab.limiter import RateLimitRule
from ratelab.store.limiters import (
    build_decision_from_reply,
    build_redis_key,
    create_redis_limiter,
)
from ratelab.store.script_loader import read_lua_sources, register_lua_scripts

pytestmark = pytest.mark.anyio

LUA_ALGORITHMS = sorted(read_lua_sources())
BURST_RULE = RateLimitRule(limit=10, window_seconds=60)


async def wait_until_inside_window(window_seconds: float, margin_seconds: float = 5.0) -> None:
    """Keep a short burst from straddling a fixed-window boundary."""
    until_boundary = window_seconds - time.time() % window_seconds
    if until_boundary < margin_seconds:
        await asyncio.sleep(until_boundary + 0.05)


def test_every_algorithm_has_a_script() -> None:
    assert LUA_ALGORITHMS == [
        "fixed_window",
        "gcra",
        "leaky_bucket",
        "leaky_bucket_queue",
        "sliding_window_counter",
        "sliding_window_log",
        "token_bucket",
    ]


def test_key_uses_a_hash_tag_and_reply_maps_to_decision() -> None:
    assert build_redis_key("items:key:k42", "gcra") == "rl:{items:key:k42}:gcra"
    decision = build_decision_from_reply([0, 10, 0, 4000, 1500, 0])
    assert (decision.is_allowed, decision.retry_after_seconds) == (False, 1.5)


@pytest.mark.parametrize(
    "algorithm", [a for a in LUA_ALGORITHMS if a != ALGORITHM_LEAKY_BUCKET_QUEUE]
)
async def test_lua_script_admits_exactly_the_capacity_in_a_burst(
    redis_client: Redis, algorithm: str
) -> None:
    await wait_until_inside_window(BURST_RULE.window_seconds)
    limiter = create_redis_limiter(
        algorithm, BURST_RULE, redis_client, register_lua_scripts(redis_client)
    )

    decisions = [await limiter.acquire("k42") for _ in range(15)]

    assert sum(decision.is_allowed for decision in decisions) == 10
    assert decisions[0].remaining == 9
    assert decisions[-1].retry_after_seconds > 0
    ttl_ms = await redis_client.pttl(build_redis_key("k42", algorithm))
    # the sliding counter still needs this window's count during the next window
    assert 0 < ttl_ms <= 2 * 60_000


async def test_leaky_queue_script_delays_requests_in_order(redis_client: Redis) -> None:
    rule = RateLimitRule(limit=10, window_seconds=1, burst=3)
    limiter = create_redis_limiter(
        ALGORITHM_LEAKY_BUCKET_QUEUE, rule, redis_client, register_lua_scripts(redis_client)
    )

    decisions = [await limiter.acquire("k42") for _ in range(4)]

    assert [d.is_allowed for d in decisions] == [True, True, True, False]
    assert decisions[0].delay_seconds < decisions[1].delay_seconds < decisions[2].delay_seconds
    assert decisions[2].delay_seconds == pytest.approx(0.2, abs=0.01)


async def test_retry_after_is_enough_with_redis_time(redis_client: Redis) -> None:
    rule = RateLimitRule(limit=10, window_seconds=1)
    limiter = create_redis_limiter(
        ALGORITHM_TOKEN_BUCKET, rule, redis_client, register_lua_scripts(redis_client)
    )
    for _ in range(10):
        await limiter.acquire("k42")

    rejected = await limiter.acquire("k42")
    # Windows timers can wake ~15 ms early relative to Redis's clock
    await asyncio.sleep(rejected.retry_after_seconds + 0.02)

    assert not rejected.is_allowed
    assert (await limiter.acquire("k42")).is_allowed


@pytest.mark.parametrize(
    ("algorithm", "should_be_exact"),
    [
        (ALGORITHM_SLIDING_WINDOW_COUNTER, True),
        (ALGORITHM_FIXED_WINDOW, True),
        (ALGORITHM_FIXED_WINDOW_INCR, True),
        (ALGORITHM_FIXED_WINDOW_NAIVE, False),
    ],
)
async def test_parallel_requests_are_exact_only_when_atomic(
    redis_client: Redis, algorithm: str, should_be_exact: bool
) -> None:
    await wait_until_inside_window(BURST_RULE.window_seconds)
    rule = RateLimitRule(limit=100, window_seconds=60)
    limiter = create_redis_limiter(
        algorithm, rule, redis_client, register_lua_scripts(redis_client)
    )

    admitted_per_burst = []
    for burst_index in range(5):
        decisions = await asyncio.gather(*(limiter.acquire(f"k{burst_index}") for _ in range(200)))
        admitted_per_burst.append(sum(decision.is_allowed for decision in decisions))

    if should_be_exact:
        assert admitted_per_burst == [100] * 5
    else:
        # the race is timing-dependent; over five bursts it shows up
        assert max(admitted_per_burst) > 100


async def test_scripts_reload_after_script_flush(redis_client: Redis) -> None:
    limiter = create_redis_limiter(
        ALGORITHM_TOKEN_BUCKET, BURST_RULE, redis_client, register_lua_scripts(redis_client)
    )
    await limiter.acquire("k42")

    await redis_client.script_flush()

    assert (await limiter.acquire("k42")).remaining == 8


async def test_cost_above_capacity_is_rejected_before_calling_redis(redis_client: Redis) -> None:
    limiter = create_redis_limiter(
        ALGORITHM_FIXED_WINDOW_NAIVE, BURST_RULE, redis_client, register_lua_scripts(redis_client)
    )

    with pytest.raises(ValueError):
        await limiter.acquire("k42", cost=11)
