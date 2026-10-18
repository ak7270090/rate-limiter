import pytest
from redis.asyncio import Redis
from redis.asyncio.cluster import RedisCluster

from ratelab.config import ApiSettings
from ratelab.redis_client import create_redis_client


@pytest.mark.parametrize(
    ("mode", "expected_type"), [("single", Redis), ("cluster", RedisCluster), ("sentinel", Redis)]
)
def test_client_type_follows_the_redis_mode(mode: str, expected_type: type) -> None:
    client = create_redis_client(ApiSettings(redis_mode=mode, redis_url="redis://localhost:1"))

    assert isinstance(client, expected_type)


def test_sentinel_client_asks_for_the_configured_service() -> None:
    settings = ApiSettings(
        redis_mode="sentinel",
        redis_sentinel_hosts=["sentinel-a:26379", "sentinel-b:26380"],
        redis_sentinel_service="primary-x",
    )

    client = create_redis_client(settings)

    assert client.connection_pool.service_name == "primary-x"
    assert [
        (
            sentinel.connection_pool.connection_kwargs["host"],
            sentinel.connection_pool.connection_kwargs["port"],
        )
        for sentinel in client.connection_pool.sentinel_manager.sentinels
    ] == [("sentinel-a", 26379), ("sentinel-b", 26380)]
