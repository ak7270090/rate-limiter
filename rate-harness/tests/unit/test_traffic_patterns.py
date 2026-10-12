import time
from collections.abc import AsyncIterator

import aiohttp
import pytest
from aiohttp.test_utils import TestServer
from stub_api import STUB_LIMIT, create_stub_api

from rateharness.client_factory import create_api_key, create_http_session, open_connections
from rateharness.config import HarnessSettings
from rateharness.traffic_patterns import (
    RequestTarget,
    next_window_boundary,
    send_boundary_straddle,
    send_fan_out,
    send_parallel,
    send_sequential,
    send_steady,
)

pytestmark = pytest.mark.anyio

ITEMS = RequestTarget("GET", "/items")


@pytest.fixture
async def stub_session() -> AsyncIterator[aiohttp.ClientSession]:
    server = TestServer(create_stub_api())
    await server.start_server()
    settings = HarnessSettings(target_url=str(server.make_url("")))
    async with create_http_session(settings) as session:
        yield session
    await server.close()


async def test_send_sequential_records_status_and_replica(
    stub_session: aiohttp.ClientSession,
) -> None:
    responses = await send_sequential(stub_session, ITEMS, create_api_key("t"), STUB_LIMIT + 2)

    assert [r.status_code for r in responses] == [200] * STUB_LIMIT + [429, 429]
    assert {r.replica_id for r in responses} == {"stub-1"}
    assert all(r.elapsed_seconds >= 0 for r in responses)


async def test_send_steady_spaces_requests_at_the_rate(
    stub_session: aiohttp.ClientSession,
) -> None:
    responses = await send_steady(stub_session, ITEMS, create_api_key("t"), 5, rate_per_second=50)

    assert len(responses) == 5
    assert responses[-1].sent_at - responses[0].sent_at == pytest.approx(0.08, abs=0.05)


async def test_send_parallel_sends_one_request_per_key(
    stub_session: aiohttp.ClientSession,
) -> None:
    keys = [create_api_key("t") for _ in range(8)]

    responses = await send_parallel(stub_session, ITEMS, keys + keys, max_parallel_requests=4)

    assert len(responses) == 16
    assert all(r.status_code == 200 for r in responses)


async def test_send_fan_out_hits_one_key_at_once(stub_session: aiohttp.ClientSession) -> None:
    responses = await send_fan_out(stub_session, ITEMS, create_api_key("t"), client_count=12)

    assert sum(r.status_code == 200 for r in responses) == STUB_LIMIT
    assert sum(r.status_code == 429 for r in responses) == 12 - STUB_LIMIT


async def test_boundary_straddle_sends_bursts_on_both_sides(
    stub_session: aiohttp.ClientSession,
) -> None:
    window_seconds = 1.0
    started = time.time()

    responses = await send_boundary_straddle(
        stub_session,
        ITEMS,
        create_api_key("t"),
        burst_size=3,
        window_seconds=window_seconds,
        lead_seconds=0.2,
        after_seconds=0.05,
        max_parallel_requests=3,
    )

    boundary = next_window_boundary(started, window_seconds, 0.2)
    gap = responses[3].sent_at - responses[2].sent_at
    assert len(responses) == 6
    assert gap == pytest.approx(0.25, abs=0.1)
    assert time.time() > boundary


async def test_open_connections_sends_one_request_each(
    stub_session: aiohttp.ClientSession,
) -> None:
    await open_connections(stub_session, 4, "/ping")

    async with stub_session.get("/ping") as response:
        assert response.status == 200


def test_next_window_boundary_leaves_room_to_prepare() -> None:
    assert next_window_boundary(100.0, 10.0, 1.0) == 110.0
    assert next_window_boundary(109.0, 10.0, 1.0) == 120.0
