"""Build the FastAPI app: Redis-backed limiters, middlewares and ``/metrics``."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from ratelab.api.caller_key import CallerKeyExtractor
from ratelab.api.middleware import RateLimitMiddleware
from ratelab.api.routes import router
from ratelab.clock import Clock
from ratelab.config import ApiSettings, get_api_settings
from ratelab.constants import REPLICA_ID_HEADER
from ratelab.metrics import metrics_router
from ratelab.policies.route_limiters import RouteLimiterFactory
from ratelab.policies.route_policies import build_policy_registry, load_route_policies
from ratelab.storage.client import create_redis_client
from ratelab.storage.failure_policy import CircuitBreaker
from ratelab.storage.script_loader import register_lua_scripts


class ReplicaIdMiddleware(BaseHTTPMiddleware):
    """Tags every response, including 429s and 503s, with the replica that answered."""

    def __init__(self, app: ASGIApp, replica_id: str) -> None:
        super().__init__(app)
        self._replica_id = replica_id

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers[REPLICA_ID_HEADER] = self._replica_id
        return response


class RedisLifespan:
    """Closes the Redis pool when the app shuts down."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    @asynccontextmanager
    async def __call__(self, app: FastAPI) -> AsyncIterator[None]:
        yield
        await self._redis.aclose()


def create_app(
    settings: ApiSettings | None = None,
    redis: Redis | None = None,
    clock: Clock | None = None,
) -> FastAPI:
    settings = settings or get_api_settings()
    redis = redis or create_redis_client(settings)
    limiter_factory = RouteLimiterFactory(
        scripts=register_lua_scripts(redis),
        breaker=CircuitBreaker(
            settings.breaker_failure_threshold, settings.breaker_open_seconds, clock
        ),
    )
    policies = load_route_policies(settings.policies_file, settings.policy_overrides)
    registry = build_policy_registry(policies, limiter_factory)

    app = FastAPI(title="Rate Limiting Lab: tiered limits", lifespan=RedisLifespan(redis))
    app.include_router(router)
    app.include_router(metrics_router)
    app.add_middleware(
        RateLimitMiddleware,
        registry=registry,
        key_extractor=CallerKeyExtractor(settings.trusted_proxy_networks),
        allow_listed_api_keys=settings.allow_listed_api_keys,
    )
    app.add_middleware(ReplicaIdMiddleware, replica_id=settings.replica_id)
    return app
