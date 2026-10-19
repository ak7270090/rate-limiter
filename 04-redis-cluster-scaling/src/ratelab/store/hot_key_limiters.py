"""Two ways to keep one busy key from loading a single Redis shard: split it, or lease tokens."""

import asyncio
import random
from dataclasses import dataclass, replace

from ratelab.clock import Clock, SystemClock
from ratelab.constants import SPLIT_KEY_SEPARATOR
from ratelab.limiter import RateLimitDecision, RateLimiter, RateLimitRule


class SplitKeyLimiter:
    """Spreads one limit over ``split_count`` sub-keys, each allowing ``limit / split_count``.

    Every sub-key has its own hash tag, so the sub-keys land on different shards. A request picks
    a sub-key at random, so it can be rejected while another sub-key still has room.
    """

    def __init__(self, sub_key_limiter: RateLimiter, split_count: int) -> None:
        self._sub_key_limiter = sub_key_limiter
        self._split_count = split_count

    async def acquire(self, key: str, cost: int = 1) -> RateLimitDecision:
        sub_key_index = random.randrange(self._split_count)
        return await self._sub_key_limiter.acquire(
            f"{key}{SPLIT_KEY_SEPARATOR}{sub_key_index}", cost
        )


def split_rule(rule: RateLimitRule, split_count: int) -> RateLimitRule:
    """The rule each sub-key enforces."""
    return RateLimitRule(
        limit=max(rule.limit // split_count, 1),
        window_seconds=rule.window_seconds,
        burst=max(rule.burst // split_count, 1) if rule.burst else None,
    )


@dataclass
class TokenLease:
    tokens: int
    expires_at: float


@dataclass(frozen=True)
class CachedRejection:
    decision: RateLimitDecision
    blocked_until: float


class TokenLeaseLimiter:
    """Takes ``lease_size`` tokens from Redis in one call and hands them out in this replica.

    Leased tokens are already counted in Redis, so the limit is never exceeded. The cost is the
    other way round: tokens a replica leased but did not use before ``lease_ttl_seconds`` are
    lost, and a replica that holds a lease serves its callers while others are rejected. Once
    Redis rejects, the replica rejects locally until the retry-after time, so rejected traffic
    stops reaching Redis.
    """

    def __init__(
        self,
        store_limiter: RateLimiter,
        lease_size: int,
        lease_ttl_seconds: float,
        clock: Clock | None = None,
    ) -> None:
        self._store_limiter = store_limiter
        self._lease_size = lease_size
        self._lease_ttl_seconds = lease_ttl_seconds
        self._clock = clock or SystemClock()
        self._leases: dict[str, TokenLease] = {}
        self._lease_locks: dict[str, asyncio.Lock] = {}
        self._rejections: dict[str, CachedRejection] = {}

    async def acquire(self, key: str, cost: int = 1) -> RateLimitDecision:
        decision = self._spend_from_lease(key, cost) or self._reject_while_exhausted(key)
        if decision is not None:
            return decision
        async with self._lease_locks.setdefault(key, asyncio.Lock()):
            decision = self._spend_from_lease(key, cost) or self._reject_while_exhausted(key)
            if decision is not None:
                return decision
            return await self._take_new_lease(key, cost)

    def _reject_while_exhausted(self, key: str) -> RateLimitDecision | None:
        """After Redis said no, answer no locally until its retry-after time has passed."""
        rejection = self._rejections.get(key)
        if rejection is None:
            return None
        retry_after_seconds = rejection.blocked_until - self._clock.now()
        if retry_after_seconds <= 0:
            del self._rejections[key]
            return None
        return replace(rejection.decision, retry_after_seconds=retry_after_seconds)

    def _spend_from_lease(self, key: str, cost: int) -> RateLimitDecision | None:
        lease = self._leases.get(key)
        if lease is None or lease.expires_at <= self._clock.now() or lease.tokens < cost:
            return None
        lease.tokens -= cost
        return RateLimitDecision(
            is_allowed=True,
            limit=self._lease_size,
            remaining=lease.tokens,
            reset_after_seconds=lease.expires_at - self._clock.now(),
        )

    async def _take_new_lease(self, key: str, cost: int) -> RateLimitDecision:
        lease_decision = await self._store_limiter.acquire(key, max(self._lease_size, cost))
        if lease_decision.is_allowed:
            self._leases[key] = TokenLease(
                tokens=max(self._lease_size, cost) - cost,
                expires_at=self._clock.now() + self._lease_ttl_seconds,
            )
            return lease_decision
        single_decision = await self._store_limiter.acquire(key, cost)
        if not single_decision.is_allowed:
            self._rejections[key] = CachedRejection(
                decision=single_decision,
                blocked_until=self._clock.now() + (single_decision.retry_after_seconds or 0.0),
            )
        return single_decision
