"""Checks every request against its route policy before the route handler runs."""

import asyncio
import hashlib
import logging
import math
import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from ratelab.api.caller_key import CallerKeyExtractor
from ratelab.api.headers import build_rate_limit_headers
from ratelab.constants import (
    API_KEY_HASH_LENGTH,
    DECISION_ALLOWED,
    DECISION_REJECTED,
    DECISION_UNAVAILABLE,
    GLOBAL_CALLER_KEY,
    LIMITER_UNAVAILABLE_DETAIL,
    RATE_LIMITED_DETAIL,
    RETRY_AFTER_HEADER,
)
from ratelab.metrics import DECISIONS, LIMITER_SECONDS
from ratelab.policies.registry import PolicyRegistry
from ratelab.store.failure_policy import LimiterUnavailableError

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Find the policy, count the caller, answer 429 / 503 or pass through with headers added."""

    def __init__(
        self,
        app: ASGIApp,
        registry: PolicyRegistry,
        key_extractor: CallerKeyExtractor,
        allow_listed_api_keys: set[str],
    ) -> None:
        super().__init__(app)
        self._registry = registry
        self._key_extractor = key_extractor
        self._allow_listed_caller_keys = {
            key_extractor.extract_caller_key_for_api_key(api_key)
            for api_key in allow_listed_api_keys
        }

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        limited_route = self._registry.find(request.method, request.url.path)
        if limited_route is None:
            return await call_next(request)
        caller_key = self._key_extractor.extract_caller_key(request)
        if caller_key in self._allow_listed_caller_keys:
            return await call_next(request)
        policy = limited_route.policy
        counted_key = GLOBAL_CALLER_KEY if policy.is_global else caller_key
        started = time.perf_counter()
        try:
            decision = await limited_route.limiter.acquire(f"{policy.name}:{counted_key}")
        except LimiterUnavailableError as error:
            DECISIONS.labels(policy.name, DECISION_UNAVAILABLE).inc()
            return JSONResponse(
                {"detail": LIMITER_UNAVAILABLE_DETAIL, "policy": policy.name},
                status_code=503,
                headers={RETRY_AFTER_HEADER: str(max(math.ceil(error.retry_after_seconds), 1))},
            )
        finally:
            LIMITER_SECONDS.labels(policy.name).observe(time.perf_counter() - started)
        headers = build_rate_limit_headers(policy, decision)
        if not decision.is_allowed:
            DECISIONS.labels(policy.name, DECISION_REJECTED).inc()
            logger.info(
                "rate limited route=%s caller=%s retry_after=%.2f",
                policy.name,
                hash_caller_key(caller_key),
                decision.retry_after_seconds,
            )
            return JSONResponse(
                {"detail": RATE_LIMITED_DETAIL, "policy": policy.name},
                status_code=429,
                headers=headers,
            )
        DECISIONS.labels(policy.name, DECISION_ALLOWED).inc()
        if decision.delay_seconds > 0:
            await asyncio.sleep(decision.delay_seconds)
        response = await call_next(request)
        response.headers.update(headers)
        return response


def hash_caller_key(caller_key: str) -> str:
    """Log a stable fingerprint instead of the raw API key."""
    return hashlib.sha256(caller_key.encode()).hexdigest()[:API_KEY_HASH_LENGTH]
