"""The shared Redis client: one node, a cluster, or the primary that Sentinel points to."""

from redis.asyncio import BlockingConnectionPool, Redis
from redis.asyncio.cluster import ClusterNode, RedisCluster
from redis.asyncio.sentinel import Sentinel
from redis.backoff import NoBackoff
from redis.retry import Retry

from ratelab.config import ApiSettings

RedisClient = Redis | RedisCluster


def create_redis_client(settings: ApiSettings) -> RedisClient:
    """One client per process, created at startup.

    Retries are off: a retried call could take several timeouts, and the circuit breaker
    already decides what to do when Redis does not answer.
    """
    if settings.redis_mode == "cluster":
        return create_cluster_client(settings)
    if settings.redis_mode == "sentinel":
        return create_sentinel_client(settings)
    return create_single_node_client(settings)


def create_single_node_client(settings: ApiSettings) -> Redis:
    """The pool blocks (up to the Redis timeout) when every connection is busy, instead of
    raising "Too many connections", which the circuit breaker would count as Redis being down."""
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


def create_cluster_client(settings: ApiSettings) -> RedisCluster:
    """Routes each script call to the primary that owns its key's slot.

    Every node is a seed, so the client can rediscover the cluster while any one node is down.
    One retry lets the client follow a MOVED reply after a failover.
    """
    seed_nodes = [
        ClusterNode(host, int(port))
        for host, port in (address.split(":") for address in settings.redis_cluster_seed_nodes)
    ]
    return RedisCluster(
        startup_nodes=seed_nodes,
        max_connections=settings.redis_max_connections,
        socket_timeout=settings.redis_timeout_seconds,
        socket_connect_timeout=settings.redis_connect_timeout_seconds,
        retry=Retry(NoBackoff(), retries=1),
        decode_responses=True,
    )


def create_sentinel_client(settings: ApiSettings) -> Redis:
    """Asks Sentinel where the primary is, and asks again after a failover."""
    sentinel_addresses = [
        (host, int(port))
        for host, port in (address.split(":") for address in settings.redis_sentinel_hosts)
    ]
    sentinel = Sentinel(
        sentinel_addresses,
        socket_timeout=settings.redis_timeout_seconds,
        socket_connect_timeout=settings.redis_connect_timeout_seconds,
    )
    return sentinel.master_for(
        settings.redis_sentinel_service,
        socket_timeout=settings.redis_timeout_seconds,
        socket_connect_timeout=settings.redis_connect_timeout_seconds,
        max_connections=settings.redis_max_connections,
        retry=Retry(NoBackoff(), retries=0),
        decode_responses=True,
    )
