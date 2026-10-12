from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from ratelab.app import create_app
from ratelab.clock import FakeClock
from ratelab.config import ApiSettings

pytestmark = pytest.mark.anyio

POLICIES = """
routes:
  - {name: items, method: GET, path: /items, algorithm: sliding_window_counter,
     limit: 3, window_seconds: 10}
  - {name: search, method: get, path: /search, algorithm: fixed_window,
     limit: 2, window_seconds: 10, scope: global}
  - {name: orders, method: POST, path: /orders, algorithm: leaky_bucket_queue,
     limit: 100, window_seconds: 1, burst: 3}
"""


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(1_000.0)


@pytest.fixture
async def client(tmp_path: Path, clock: FakeClock) -> AsyncIterator[httpx.AsyncClient]:
    policies_file = tmp_path / "policies.yaml"
    policies_file.write_text(POLICIES, encoding="utf-8")
    settings = ApiSettings(
        policies_file=policies_file, replica_id="replica-test", allow_listed_api_keys={"vip"}
    )
    transport = httpx.ASGITransport(app=create_app(settings, clock))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


async def test_unlimited_route_has_replica_id_but_no_limit_headers(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/ping")

    assert response.status_code == 200
    assert response.headers["X-Replica-Id"] == "replica-test"
    assert "RateLimit" not in response.headers


async def test_per_key_limit_then_429_with_headers(client: httpx.AsyncClient) -> None:
    headers = {"X-API-Key": "k42"}
    allowed = [await client.get("/items", headers=headers) for _ in range(3)]
    rejected = await client.get("/items", headers=headers)
    other_key = await client.get("/items", headers={"X-API-Key": "k43"})

    assert [response.status_code for response in allowed] == [200, 200, 200]
    assert allowed[0].headers["RateLimit-Policy"] == '"items";q=3;w=10'
    assert allowed[0].headers["RateLimit"] == '"items";r=2;t=20'
    assert rejected.status_code == 429
    assert rejected.json() == {"detail": "rate limit exceeded", "policy": "items"}
    # 3 in this window: room again once the previous-window weight drops to 2/3, 13.3 s later
    assert rejected.headers["Retry-After"] == "14"
    assert rejected.headers["X-Replica-Id"] == "replica-test"
    assert other_key.status_code == 200


async def test_global_scope_is_shared_by_all_callers(client: httpx.AsyncClient) -> None:
    statuses = [
        (await client.get("/search", headers={"X-API-Key": f"k{index}"})).status_code
        for index in range(3)
    ]

    assert statuses == [200, 200, 429]


async def test_allow_listed_key_is_never_limited(client: httpx.AsyncClient) -> None:
    statuses = {
        (await client.get("/items", headers={"X-API-Key": "vip"})).status_code for _ in range(5)
    }

    assert statuses == {200}


async def test_leaky_queue_delays_then_rejects_when_full(client: httpx.AsyncClient) -> None:
    statuses = [(await client.post("/orders")).status_code for _ in range(4)]

    assert statuses == [200, 200, 200, 429]
