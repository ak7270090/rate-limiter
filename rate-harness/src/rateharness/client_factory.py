"""HTTP sessions and API keys for talking to the API under test.

The harness uses aiohttp: with 50+ requests in flight from one process it sustains about ten
times the throughput of httpx, and a slow client would blur every timing-based check.
"""

import asyncio
from uuid import uuid4

import aiohttp

from rateharness.config import HarnessSettings
from rateharness.constants import API_KEY_HEADER


def create_http_session(settings: HarnessSettings) -> aiohttp.ClientSession:
    """Create a session whose connector keeps up to ``connection_pool_size`` connections."""
    return aiohttp.ClientSession(
        base_url=settings.target_url,
        connector=aiohttp.TCPConnector(limit=settings.connection_pool_size),
        timeout=aiohttp.ClientTimeout(total=settings.request_timeout_seconds),
    )


async def open_connections(
    session: aiohttp.ClientSession, connection_count: int, path: str
) -> None:
    """Open ``connection_count`` connections up front with parallel requests to ``path``.

    Opening a connection through Docker Desktop's port forwarding can take far longer than a
    request, so timed bursts must not pay for it.
    """
    await asyncio.gather(*(_read_once(session, path) for _ in range(connection_count)))


def build_api_key_headers(api_key: str) -> dict[str, str]:
    """Headers that identify the caller to the rate limiter."""
    return {API_KEY_HEADER: api_key}


def create_api_key(prefix: str) -> str:
    """A fresh API key, so each test starts with an empty limit."""
    return f"{prefix}-{uuid4().hex[:12]}"


async def _read_once(session: aiohttp.ClientSession, path: str) -> None:
    async with session.get(path) as response:
        await response.read()
