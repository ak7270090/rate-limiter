"""Limiters whose state lives in Redis: one Lua script per algorithm, plus two variants without
Lua that show why the script is needed."""

import math

from redis.asyncio import Redis
from redis.commands.core import AsyncScript

from ratelab.algorithm_registry import IN_MEMORY_LIMITERS
from ratelab.clock import Clock, SystemClock
from ratelab.constants import (
    ALGORITHM_FIXED_WINDOW_INCR,
    ALGORITHM_FIXED_WINDOW_NAIVE,
    REDIS_KEY_PREFIX,
)
from ratelab.rate_limiter import (
    RateLimitDecision,
    RateLimiter,
    RateLimitRule,
    build_decision,
    ensure_cost_fits,
)

REDIS_ALGORITHMS = frozenset(IN_MEMORY_LIMITERS) | {
    ALGORITHM_FIXED_WINDOW_NAIVE,
    ALGORITHM_FIXED_WINDOW_INCR,
}


def build_redis_key(counted_key: str, algorithm: str) -> str:
    """``rl:{items:key:k42}:gcra``: the hash tag keeps all of one caller's keys in one slot."""
    return f"{REDIS_KEY_PREFIX}:{{{counted_key}}}:{algorithm}"


def build_decision_from_reply(reply: list[int]) -> RateLimitDecision:
    """Turn ``{allowed, limit, remaining, reset_ms, retry_ms, delay_ms}`` into a decision."""
    allowed, limit, remaining, reset_ms, retry_ms, delay_ms = (int(value) for value in reply)
    is_allowed = allowed == 1
    return RateLimitDecision(
        is_allowed=is_allowed,
        limit=limit,
        remaining=remaining,
        reset_after_seconds=reset_ms / 1000,
        retry_after_seconds=None if is_allowed else retry_ms / 1000,
        delay_seconds=delay_ms / 1000,
    )


class LuaScriptLimiter:
    """Read, decide and write in one script call; Redis runs scripts one at a time.

    The script reads Redis's own clock, so replicas with skewed clocks still agree.
    """

    def __init__(self, algorithm: str, rule: RateLimitRule, script: AsyncScript) -> None:
        self.rule = rule
        self._algorithm = algorithm
        self._script = script

    async def acquire(self, key: str, cost: int = 1) -> RateLimitDecision:
        ensure_cost_fits(cost, self.rule)
        reply = await self._script(
            keys=[build_redis_key(key, self._algorithm)],
            args=[self.rule.limit, self.rule.window_seconds, cost, self.rule.capacity],
        )
        return build_decision_from_reply(reply)


class NaiveFixedWindowLimiter:
    """GET, compare in Python, then INCRBY. Two replicas can both read 99 and both allow."""

    def __init__(self, rule: RateLimitRule, redis: Redis, clock: Clock | None = None) -> None:
        self.rule = rule
        self._redis = redis
        self._clock = clock or SystemClock()

    async def acquire(self, key: str, cost: int = 1) -> RateLimitDecision:
        ensure_cost_fits(cost, self.rule)
        window_key, reset_after_seconds = _current_window_key(
            key, ALGORITHM_FIXED_WINDOW_NAIVE, self.rule, self._clock
        )
        count = int(await self._redis.get(window_key) or 0)
        if count + cost > self.rule.limit:
            return _fixed_window_decision(False, self.rule, count, reset_after_seconds)
        count = await self._redis.incrby(window_key, cost)
        await self._redis.expire(window_key, math.ceil(self.rule.window_seconds))
        return _fixed_window_decision(True, self.rule, count, reset_after_seconds)


class IncrFixedWindowLimiter:
    """INCRBY first, compare after: atomic without Lua. ``EXPIRE NX`` sets the TTL only once.

    The window comes from the replica's clock, unlike the Lua scripts.
    """

    def __init__(self, rule: RateLimitRule, redis: Redis, clock: Clock | None = None) -> None:
        self.rule = rule
        self._redis = redis
        self._clock = clock or SystemClock()

    async def acquire(self, key: str, cost: int = 1) -> RateLimitDecision:
        ensure_cost_fits(cost, self.rule)
        window_key, reset_after_seconds = _current_window_key(
            key, ALGORITHM_FIXED_WINDOW_INCR, self.rule, self._clock
        )
        async with self._redis.pipeline(transaction=True) as pipeline:
            pipeline.incrby(window_key, cost)
            pipeline.expire(window_key, math.ceil(self.rule.window_seconds), nx=True)
            count, _ = await pipeline.execute()
        is_allowed = count <= self.rule.limit
        return _fixed_window_decision(is_allowed, self.rule, count, reset_after_seconds)


def create_redis_limiter(
    algorithm: str,
    rule: RateLimitRule,
    redis: Redis,
    scripts: dict[str, AsyncScript],
    clock: Clock | None = None,
) -> RateLimiter:
    """The Redis limiter for ``algorithm``; raises ``KeyError`` for an unknown name."""
    if algorithm == ALGORITHM_FIXED_WINDOW_NAIVE:
        return NaiveFixedWindowLimiter(rule, redis, clock)
    if algorithm == ALGORITHM_FIXED_WINDOW_INCR:
        return IncrFixedWindowLimiter(rule, redis, clock)
    return LuaScriptLimiter(algorithm, rule, scripts[algorithm])


def _current_window_key(
    key: str, algorithm: str, rule: RateLimitRule, clock: Clock
) -> tuple[str, float]:
    now = clock.now()
    window_start = math.floor(now / rule.window_seconds) * rule.window_seconds
    window_key = f"{build_redis_key(key, algorithm)}:{int(window_start)}"
    return window_key, window_start + rule.window_seconds - now


def _fixed_window_decision(
    is_allowed: bool, rule: RateLimitRule, count: int, reset_after_seconds: float
) -> RateLimitDecision:
    return build_decision(
        is_allowed=is_allowed,
        limit=rule.limit,
        remaining=rule.limit - count,
        reset_after_seconds=reset_after_seconds,
        retry_after_seconds=reset_after_seconds,
    )
