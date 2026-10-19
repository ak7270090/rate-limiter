from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from redis.asyncio import Redis

from ratelab.app import create_app
from ratelab.config import ApiSettings
from ratelab.storage.client import create_redis_client

pytestmark = pytest.mark.anyio

POLICIES = """
routes:
  - name: items
    method: GET
    path: /items
    tiers:
      - {name: items, scope: route_caller, algorithm: sliding_window_counter, limit: 3,
         window_seconds: 10}
      - {name: global, scope: global, algorithm: gcra, limit: 100, window_seconds: 1}
  - name: search
    method: GET
    path: /search
    mode: shadow
    tiers:
      - {name: search, scope: route, algorithm: fixed_window, limit: 1, window_seconds: 60}
  - name: orders
    method: POST
    path: /orders
    on_store_failure: reject
    tiers:
      - {name: orders, scope: route_caller, algorithm: gcra, limit: 10, window_seconds: 60}
"""


def build_settings(tmp_path: Path, redis_url: str) -> ApiSettings:
    policies_file = tmp_path / "policies.yaml"
    policies_file.write_text(POLICIES, encoding="utf-8")
    return ApiSettings(
        policies_file=policies_file,
        replica_id="replica-test",
        allow_listed_api_keys={"vip"},
        redis_url=redis_url,
    )


async def open_client(settings: ApiSettings, redis: Redis) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=create_app(settings, redis))
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


@pytest.fixture
async def client(tmp_path: Path, redis_client: Redis) -> AsyncIterator[httpx.AsyncClient]:
    async with await open_client(build_settings(tmp_path, "unused"), redis_client) as client:
        yield client


@pytest.fixture
async def client_without_redis(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    settings = build_settings(tmp_path, "redis://127.0.0.1:1/0")
    redis = create_redis_client(settings)
    async with await open_client(settings, redis) as client:
        yield client
    await redis.aclose()


async def test_tiers_limit_and_report_every_tier(client: httpx.AsyncClient) -> None:
    headers = {"X-API-Key": "k42"}
    statuses = [(await client.get("/items", headers=headers)).status_code for _ in range(4)]
    rejected = await client.get("/items", headers=headers)
    allow_listed = {(await client.get("/items", headers={"X-API-Key": "vip"})).status_code}

    assert statuses == [200, 200, 200, 429]
    assert rejected.headers["RateLimit-Policy"] == '"items";q=3;w=10, "global";q=100;w=1'
    assert rejected.headers["RateLimit"].startswith('"items";r=0;')
    assert rejected.json() == {"detail": "rate limit exceeded", "policy": "items"}
    assert int(rejected.headers["Retry-After"]) >= 1
    assert rejected.headers["X-Replica-Id"] == "replica-test"
    assert allow_listed == {200}


async def test_shadow_mode_records_but_never_rejects(client: httpx.AsyncClient) -> None:
    statuses = [(await client.get("/search")).status_code for _ in range(3)]
    metrics = (await client.get("/metrics")).text

    assert statuses == [200, 200, 200]
    assert 'ratelab_decisions_total{decision="shadow_rejected",route="search"} 2.0' in metrics


async def test_redis_down_follows_each_routes_policy(
    client_without_redis: httpx.AsyncClient,
) -> None:
    items = [(await client_without_redis.get("/items")).status_code for _ in range(4)]
    orders = await client_without_redis.post("/orders")

    assert items == [200] * 4
    assert orders.status_code == 503
    assert orders.json()["detail"] == "rate limiter unavailable"
