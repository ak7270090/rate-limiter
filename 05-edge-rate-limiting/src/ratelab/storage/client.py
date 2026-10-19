"""The shared Redis connection pool."""

from redis.asyncio import BlockingConnectionPool, Redis
from redis.backoff import NoBackoff
from redis.retry import Retry

from ratelab.config import ApiSettings


def create_redis_client(settings: ApiSettings) -> Redis:
    """One pool per process, created at startup.

    The pool blocks (up to the Redis timeout) when every connection is busy, instead of raising
    "Too many connections", which the circuit breaker would count as Redis being down.
    Retries are off: a retried call could take several timeouts.
    """
    connection_pool = BlockingConnectionPool.from_url(
        settings.redis_url,
        max_connections=settings.redis_max_connections,
        timeout=settings.redis_timeout_seconds,
        socket_timeout=settings.redis_timeout_seconds,
        socket_connect_timeout=settings.redis_connect_timeout_seconds,
        retry=Retry(NoBackoff(), retries=0),
        decode_responses=True,
    )
    return Redis(connection_pool=connection_pool)
