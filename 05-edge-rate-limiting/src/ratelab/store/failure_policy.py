"""What a route does when Redis is slow or down: allow or reject."""

import logging

from ratelab.clock import Clock, SystemClock
from ratelab.constants import ON_STORE_FAILURE_ALLOW, ON_STORE_FAILURE_REJECT
from ratelab.metrics import STORE_FAILURES
from ratelab.rate_limiter import RateLimitDecision, RateLimiter

logger = logging.getLogger(__name__)


class LimiterUnavailableError(Exception):
    """A fail-closed route cannot decide; answer 503."""

    def __init__(self, retry_after_seconds: float) -> None:
        super().__init__("rate limiter store unavailable")
        self.retry_after_seconds = retry_after_seconds


class CircuitBreaker:
    """After ``failure_threshold`` failures in a row, skip Redis for ``open_seconds``.

    Without it every request on a dead Redis would wait for the full timeout. After the open
    period one request tries Redis again; a failure opens the breaker again at once.
    """

    def __init__(
        self, failure_threshold: int, open_seconds: float, clock: Clock | None = None
    ) -> None:
        self.open_seconds = open_seconds
        self._failure_threshold = failure_threshold
        self._clock = clock or SystemClock()
        self._consecutive_failures = 0
        self._open_until = 0.0

    @property
    def is_open(self) -> bool:
        return self._clock.now() < self._open_until

    def record_success(self) -> None:
        self._consecutive_failures = 0
        self._open_until = 0.0

    def record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._failure_threshold:
            self._open_until = self._clock.now() + self.open_seconds


class StoreFailurePolicyLimiter:
    """Asks the Redis limiter, and applies the route's ``on_store_failure`` when that fails."""

    def __init__(
        self,
        route_name: str,
        fail_open_limit: int,
        store_limiter: RateLimiter,
        breaker: CircuitBreaker,
        on_store_failure: str,
    ) -> None:
        if on_store_failure not in (ON_STORE_FAILURE_ALLOW, ON_STORE_FAILURE_REJECT):
            raise ValueError(f"unknown on_store_failure {on_store_failure!r}")
        self._route_name = route_name
        self._fail_open_limit = fail_open_limit
        self._store_limiter = store_limiter
        self._breaker = breaker
        self._on_store_failure = on_store_failure

    async def acquire(self, key: str, cost: int = 1) -> RateLimitDecision:
        if not self._breaker.is_open:
            try:
                decision = await self._store_limiter.acquire(key, cost)
            # Any store fault applies the route's policy, not only Redis errors (phase 4 saw
            # redis-py raise RuntimeError on connections closed after a timeout).
            except Exception as error:
                self._breaker.record_failure()
                logger.warning(
                    "redis failed route=%s error=%s: %s",
                    self._route_name,
                    type(error).__name__,
                    error,
                )
            else:
                self._breaker.record_success()
                return decision
        STORE_FAILURES.labels(self._route_name, self._on_store_failure).inc()
        if self._on_store_failure == ON_STORE_FAILURE_REJECT:
            raise LimiterUnavailableError(self._breaker.open_seconds)
        return RateLimitDecision(
            is_allowed=True,
            limit=self._fail_open_limit,
            remaining=self._fail_open_limit,
            reset_after_seconds=0.0,
        )
