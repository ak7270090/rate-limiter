"""The four traffic shapes the suites send: steady, burst, boundary straddle and fan-out."""

import math
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import aiohttp
import anyio
from multidict import CIMultiDict

from rateharness.client_factory import build_api_key_headers
from rateharness.constants import REPLICA_ID_HEADER


@dataclass(frozen=True)
class ObservedResponse:
    """One response, with when it was sent and how long it took."""

    sent_at: float
    elapsed_seconds: float
    status_code: int
    headers: CIMultiDict[str]

    @property
    def replica_id(self) -> str | None:
        return self.headers.get(REPLICA_ID_HEADER)


@dataclass(frozen=True)
class RequestTarget:
    """Method and path of the route under test."""

    method: str
    path: str


async def send_request(
    session: aiohttp.ClientSession, target: RequestTarget, api_key: str
) -> ObservedResponse:
    """Send one request and record its timing."""
    sent_at = time.perf_counter()
    async with session.request(
        target.method, target.path, headers=build_api_key_headers(api_key)
    ) as response:
        await response.read()
    return ObservedResponse(
        sent_at=sent_at,
        elapsed_seconds=time.perf_counter() - sent_at,
        status_code=response.status,
        headers=CIMultiDict(response.headers),
    )


async def send_sequential(
    session: aiohttp.ClientSession, target: RequestTarget, api_key: str, request_count: int
) -> list[ObservedResponse]:
    """Send requests one after another, each waiting for the previous response."""
    return [await send_request(session, target, api_key) for _ in range(request_count)]


async def send_steady(
    session: aiohttp.ClientSession,
    target: RequestTarget,
    api_key: str,
    request_count: int,
    rate_per_second: float,
) -> list[ObservedResponse]:
    """Send requests at a fixed rate, starting each on schedule even if earlier ones are slow."""
    responses: list[ObservedResponse] = []
    interval_seconds = 1.0 / rate_per_second
    started_at = time.perf_counter()
    async with anyio.create_task_group() as task_group:
        for request_index in range(request_count):
            delay_seconds = started_at + request_index * interval_seconds - time.perf_counter()
            if delay_seconds > 0:
                await anyio.sleep(delay_seconds)
            task_group.start_soon(_send_and_collect, session, target, api_key, responses)
    return sorted(responses, key=lambda response: response.sent_at)


async def send_parallel(
    session: aiohttp.ClientSession,
    target: RequestTarget,
    api_keys: Sequence[str],
    max_parallel_requests: int,
) -> list[ObservedResponse]:
    """Send one request per entry in ``api_keys``, at most ``max_parallel_requests`` at a time."""
    responses: list[ObservedResponse] = []
    capacity_limiter = anyio.CapacityLimiter(max_parallel_requests)
    async with anyio.create_task_group() as task_group:
        for api_key in api_keys:
            task_group.start_soon(
                _send_with_capacity_limit, session, target, api_key, responses, capacity_limiter
            )
    return sorted(responses, key=lambda response: response.sent_at)


async def send_fan_out(
    session: aiohttp.ClientSession, target: RequestTarget, api_key: str, client_count: int
) -> list[ObservedResponse]:
    """Release ``client_count`` requests for the same key at the same instant."""
    responses: list[ObservedResponse] = []
    start_signal = anyio.Event()
    async with anyio.create_task_group() as task_group:
        for _ in range(client_count):
            task_group.start_soon(
                _send_after_signal, session, target, api_key, responses, start_signal
            )
        await anyio.sleep(0.05)
        start_signal.set()
    return sorted(responses, key=lambda response: response.sent_at)


async def send_boundary_straddle(
    session: aiohttp.ClientSession,
    target: RequestTarget,
    api_key: str,
    burst_size: int,
    window_seconds: float,
    lead_seconds: float,
    after_seconds: float,
    max_parallel_requests: int,
    wall_clock: Callable[[], float] = time.time,
) -> list[ObservedResponse]:
    """Send one burst just before a window boundary and one just after it.

    Fixed windows start at multiples of ``window_seconds`` since the Unix epoch, so the
    harness knows where the boundary is without asking the server.
    """
    boundary = next_window_boundary(wall_clock(), window_seconds, lead_seconds)
    await anyio.sleep(max(boundary - lead_seconds - wall_clock(), 0.0))
    burst_keys = [api_key] * burst_size
    before = await send_parallel(session, target, burst_keys, max_parallel_requests)
    await anyio.sleep(max(boundary + after_seconds - wall_clock(), 0.0))
    after = await send_parallel(session, target, burst_keys, max_parallel_requests)
    return before + after


async def wait_for_room_in_window(
    window_seconds: float, needed_seconds: float, wall_clock: Callable[[], float] = time.time
) -> None:
    """Start right after a window boundary if the traffic would otherwise cross one.

    Only ``boundary_burst`` is about window resets; the other suites must not hit one by luck.
    """
    seconds_left = window_seconds - wall_clock() % window_seconds
    if seconds_left < needed_seconds:
        await anyio.sleep(seconds_left + 0.05)


def next_window_boundary(now: float, window_seconds: float, minimum_lead_seconds: float) -> float:
    """The next epoch-aligned boundary that leaves at least ``minimum_lead_seconds`` to prepare."""
    boundary = math.ceil(now / window_seconds) * window_seconds
    while boundary - now < minimum_lead_seconds + 0.5:
        boundary += window_seconds
    return boundary


async def _send_and_collect(
    session: aiohttp.ClientSession,
    target: RequestTarget,
    api_key: str,
    responses: list[ObservedResponse],
) -> None:
    responses.append(await send_request(session, target, api_key))


async def _send_with_capacity_limit(
    session: aiohttp.ClientSession,
    target: RequestTarget,
    api_key: str,
    responses: list[ObservedResponse],
    capacity_limiter: anyio.CapacityLimiter,
) -> None:
    async with capacity_limiter:
        responses.append(await send_request(session, target, api_key))


async def _send_after_signal(
    session: aiohttp.ClientSession,
    target: RequestTarget,
    api_key: str,
    responses: list[ObservedResponse],
    start_signal: anyio.Event,
) -> None:
    await start_signal.wait()
    responses.append(await send_request(session, target, api_key))
