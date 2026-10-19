"""Build each route's limiter: Redis first, the hot-key strategy around it, then the route's
failure policy around both."""

from redis.commands.core import AsyncScript

from ratelab.algorithms.registry import IN_MEMORY_LIMITERS, create_in_memory_limiter
from ratelab.clock import Clock
from ratelab.constants import (
    ALGORITHM_SLIDING_WINDOW_COUNTER,
    HOT_KEY_STRATEGY_LEASE,
    HOT_KEY_STRATEGY_SPLIT,
    ON_STORE_FAILURE_LOCAL,
)
from ratelab.limiter import RateLimiter, RateLimitRule
from ratelab.policies.registry import RoutePolicy
from ratelab.store.client import RedisClient
from ratelab.store.failure_policy import CircuitBreaker, StoreFailurePolicyLimiter
from ratelab.store.hot_key_limiters import SplitKeyLimiter, TokenLeaseLimiter, split_rule
from ratelab.store.limiters import create_redis_limiter


class RouteLimiterFactory:
    """Creates a ``StoreFailurePolicyLimiter`` per route, all sharing one circuit breaker."""

    def __init__(
        self,
        redis: RedisClient,
        scripts: dict[str, AsyncScript],
        breaker: CircuitBreaker,
        replica_count_for_local_fallback: int,
        clock: Clock | None = None,
    ) -> None:
        self._redis = redis
        self._scripts = scripts
        self._breaker = breaker
        self._replica_count = replica_count_for_local_fallback
        self._clock = clock

    def __call__(self, policy: RoutePolicy) -> RateLimiter:
        local_limiter = None
        if policy.on_store_failure == ON_STORE_FAILURE_LOCAL:
            local_limiter = self.create_local_fallback(policy)
        return StoreFailurePolicyLimiter(
            route_name=policy.name,
            rule=policy.rule,
            store_limiter=self.create_store_limiter(policy),
            breaker=self._breaker,
            on_store_failure=policy.on_store_failure,
            local_limiter=local_limiter,
        )

    def create_store_limiter(self, policy: RoutePolicy) -> RateLimiter:
        """The Redis limiter, split over sub-keys or behind a token lease if the policy says so."""
        if policy.hot_key_strategy == HOT_KEY_STRATEGY_SPLIT:
            sub_key_rule = split_rule(policy.rule, policy.split_count)
            return SplitKeyLimiter(
                self._create_redis_limiter(policy, sub_key_rule), policy.split_count
            )
        redis_limiter = self._create_redis_limiter(policy, policy.rule)
        if policy.hot_key_strategy == HOT_KEY_STRATEGY_LEASE:
            return TokenLeaseLimiter(
                redis_limiter,
                lease_size=min(policy.lease_size, policy.rule.capacity),
                lease_ttl_seconds=policy.lease_ttl_seconds,
                clock=self._clock,
            )
        return redis_limiter

    def create_local_fallback(self, policy: RoutePolicy) -> RateLimiter:
        """Each replica counts on its own at ``1 / replicas`` of the limit while Redis is down."""
        rule = policy.rule
        share = self._replica_count
        local_rule = RateLimitRule(
            limit=max(rule.limit // share, 1),
            window_seconds=rule.window_seconds,
            burst=max(rule.burst // share, 1) if rule.burst else None,
        )
        algorithm = (
            policy.algorithm
            if policy.algorithm in IN_MEMORY_LIMITERS
            else ALGORITHM_SLIDING_WINDOW_COUNTER
        )
        return create_in_memory_limiter(algorithm, local_rule, self._clock)

    def _create_redis_limiter(self, policy: RoutePolicy, rule: RateLimitRule) -> RateLimiter:
        return create_redis_limiter(policy.algorithm, rule, self._redis, self._scripts, self._clock)
