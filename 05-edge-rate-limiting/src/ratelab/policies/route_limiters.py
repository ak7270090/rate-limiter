"""Build each route's limiter: its tiers in Redis, the route's failure policy around them."""

from redis.commands.core import AsyncScript

from ratelab.constants import TIERED_LIMIT_SCRIPT
from ratelab.policy_registry import RoutePolicy
from ratelab.rate_limiter import RateLimiter
from ratelab.redis_failure_policy import CircuitBreaker, StoreFailurePolicyLimiter
from ratelab.tiered_limiter import TieredLimiter


class RouteLimiterFactory:
    """Creates a ``StoreFailurePolicyLimiter`` per route, all sharing one circuit breaker."""

    def __init__(self, scripts: dict[str, AsyncScript], breaker: CircuitBreaker) -> None:
        self._script = scripts[TIERED_LIMIT_SCRIPT]
        self._breaker = breaker

    def __call__(self, policy: RoutePolicy) -> RateLimiter:
        return StoreFailurePolicyLimiter(
            route_name=policy.name,
            fail_open_limit=policy.tiers[0].limit,
            store_limiter=TieredLimiter(policy, self._script),
            breaker=self._breaker,
            on_store_failure=policy.on_store_failure,
        )
