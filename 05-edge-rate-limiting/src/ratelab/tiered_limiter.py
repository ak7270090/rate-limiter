"""Check every tier of a route in one Lua script; charge them only if all allow."""

from redis.commands.core import AsyncScript

from ratelab.constants import (
    REDIS_KEY_PREFIX,
    TIER_SCOPE_CALLER,
    TIER_SCOPE_GLOBAL,
    TIER_SCOPE_ROUTE,
)
from ratelab.policy_registry import RoutePolicy, TierPolicy
from ratelab.rate_limiter import RateLimitDecision, TierState, ensure_cost_fits

REPLY_HEADER_LENGTH = 3
VALUES_PER_TIER = 3


def build_tier_key(tier: TierPolicy, route_name: str, caller_key: str) -> str:
    """``rl:{global}:global``, ``rl:{orders-all:orders}``, ``rl:{user:key:k42}``, ..."""
    if tier.scope == TIER_SCOPE_GLOBAL:
        counted = tier.name
    elif tier.scope == TIER_SCOPE_ROUTE:
        counted = f"{tier.name}:{route_name}"
    elif tier.scope == TIER_SCOPE_CALLER:
        counted = f"{tier.name}:{caller_key}"
    else:
        counted = f"{tier.name}:{route_name}:{caller_key}"
    return f"{REDIS_KEY_PREFIX}:{{{counted}}}:{tier.algorithm}"


class TieredLimiter:
    """One route's tiers, decided together.

    The keys of different tiers hash to different slots, so this needs one Redis node (or a
    shared hash tag, which would put every caller's counters on the same shard).
    """

    def __init__(self, policy: RoutePolicy, script: AsyncScript) -> None:
        self._policy = policy
        self._script = script
        self._smallest_rule = min((tier.rule for tier in policy.tiers), key=lambda r: r.capacity)

    async def acquire(self, key: str, cost: int = 1) -> RateLimitDecision:
        ensure_cost_fits(cost, self._smallest_rule)
        tiers = self._policy.tiers
        arguments: list[str | int | float] = [cost]
        for tier in tiers:
            arguments += [tier.algorithm, tier.limit, tier.window_seconds, tier.rule.capacity]
        reply = await self._script(
            keys=[build_tier_key(tier, self._policy.name, key) for tier in tiers],
            args=arguments,
        )
        return self._build_decision([int(value) for value in reply])

    def _build_decision(self, reply: list[int]) -> RateLimitDecision:
        allowed, rejecting_tier, retry_ms = reply[:REPLY_HEADER_LENGTH]
        tier_states = tuple(
            TierState(
                name=tier.name,
                limit=reply[start],
                window_seconds=tier.window_seconds,
                remaining=reply[start + 1],
                reset_after_seconds=reply[start + 2] / 1000,
            )
            for tier, start in zip(
                self._policy.tiers,
                range(REPLY_HEADER_LENGTH, len(reply), VALUES_PER_TIER),
                strict=True,
            )
        )
        first = tier_states[0]
        return RateLimitDecision(
            is_allowed=allowed == 1,
            limit=first.limit,
            remaining=first.remaining,
            reset_after_seconds=first.reset_after_seconds,
            retry_after_seconds=None if allowed == 1 else retry_ms / 1000,
            tier_states=tier_states,
            rejected_by=self._policy.tiers[rejecting_tier - 1].name if rejecting_tier else None,
        )
