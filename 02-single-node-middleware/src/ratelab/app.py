"""Build the FastAPI app with its middlewares."""

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from ratelab.clock import Clock
from ratelab.config import ApiSettings, get_api_settings
from ratelab.constants import REPLICA_ID_HEADER
from ratelab.key_extractor import CallerKeyExtractor
from ratelab.policy_registry import build_policy_registry, load_route_policies
from ratelab.rate_limit_middleware import RateLimitMiddleware
from ratelab.routes import router


class ReplicaIdMiddleware(BaseHTTPMiddleware):
    """Tags every response, including 429s, with the replica that answered."""

    def __init__(self, app: ASGIApp, replica_id: str) -> None:
        super().__init__(app)
        self._replica_id = replica_id

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers[REPLICA_ID_HEADER] = self._replica_id
        return response


def create_app(settings: ApiSettings | None = None, clock: Clock | None = None) -> FastAPI:
    settings = settings or get_api_settings()
    registry = build_policy_registry(load_route_policies(settings.policies_file), clock)
    app = FastAPI(title="Rate Limiting Lab: single-node middleware")
    app.include_router(router)
    app.add_middleware(
        RateLimitMiddleware,
        registry=registry,
        key_extractor=CallerKeyExtractor(settings.trusted_proxy_networks),
        allow_listed_api_keys=settings.allow_listed_api_keys,
    )
    app.add_middleware(ReplicaIdMiddleware, replica_id=settings.replica_id)
    return app
