import os
from collections.abc import AsyncIterator

import pytest
from redis.asyncio import BlockingConnectionPool, Redis
from redis.exceptions import RedisError

TEST_REDIS_URL = os.environ.get("RATELAB_TEST_REDIS_URL", "redis://localhost:6379/15")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def redis_client() -> AsyncIterator[Redis]:
    """A real Redis (Lua under fakeredis differs); the test is skipped if none is running."""
    pool = BlockingConnectionPool.from_url(
        TEST_REDIS_URL,
        max_connections=50,
        timeout=5,
        socket_connect_timeout=0.5,
        decode_responses=True,
    )
    client = Redis(connection_pool=pool)
    try:
        await client.ping()
    except (RedisError, OSError):
        await client.aclose()
        pytest.skip(f"no Redis at {TEST_REDIS_URL}; run: docker compose up -d redis")
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()
