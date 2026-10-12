"""HTTP clients and API keys for talking to the API under test."""

from uuid import uuid4

import httpx

from rateharness.config import HarnessSettings
from rateharness.constants import API_KEY_HEADER


def create_http_client(
    settings: HarnessSettings,
    *,
    should_reuse_connections: bool = True,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.AsyncClient:
    """Create a client for the target; without connection reuse every request opens its own."""
    keepalive_connections = settings.max_parallel_requests if should_reuse_connections else 0
    limits = httpx.Limits(
        max_connections=settings.max_parallel_requests * 4,
        max_keepalive_connections=keepalive_connections,
    )
    return httpx.AsyncClient(
        base_url=settings.target_url,
        timeout=settings.request_timeout_seconds,
        limits=limits,
        transport=transport,
    )


def build_api_key_headers(api_key: str) -> dict[str, str]:
    """Headers that identify the caller to the rate limiter."""
    return {API_KEY_HEADER: api_key}


def create_api_key(prefix: str) -> str:
    """A fresh API key, so each test starts with an empty limit."""
    return f"{prefix}-{uuid4().hex[:12]}"
