"""Checks every request against its route policy before the route handler runs."""

import asyncio
import hashlib
import logging

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from ratelab.constants import API_KEY_HASH_LENGTH, GLOBAL_CALLER_KEY, RATE_LIMITED_DETAIL
from ratelab.key_extractor import CallerKeyExtractor
from ratelab.policy_registry import PolicyRegistry
from ratelab.rate_limit_headers import build_rate_limit_headers

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Find the policy, count the caller, answer 429 or pass through with the headers added."""

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
        decision = await limited_route.limiter.acquire(f"{policy.name}:{counted_key}")
        headers = build_rate_limit_headers(policy, decision)
        if not decision.is_allowed:
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
        if decision.delay_seconds > 0:
            await asyncio.sleep(decision.delay_seconds)
        response = await call_next(request)
        response.headers.update(headers)
        return response


def hash_caller_key(caller_key: str) -> str:
    """Log a stable fingerprint instead of the raw API key."""
    return hashlib.sha256(caller_key.encode()).hexdigest()[:API_KEY_HASH_LENGTH]
