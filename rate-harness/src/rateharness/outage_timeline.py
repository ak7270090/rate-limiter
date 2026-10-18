"""Steady traffic on one route while commands break and restore the store; reports every second.

``python -m rateharness.outage_timeline --path /items --rate 20 --seconds 40
--event "10=docker stop ratelab-phase4-redis-node-1-1" --event "30=docker start ..."
--output results/cluster-failover.md``
"""

import argparse
import shlex
import statistics
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import aiohttp
import anyio
from multidict import CIMultiDict

from rateharness.client_factory import create_api_key, create_http_session, open_connections
from rateharness.config import HarnessSettings
from rateharness.constants import (
    STATUS_OK,
    STATUS_SERVICE_UNAVAILABLE,
    STATUS_TOO_MANY_REQUESTS,
)
from rateharness.traffic_patterns import ObservedResponse, RequestTarget, send_request

STATUS_CLIENT_ERROR = 0
ADMISSION_WINDOW_SECONDS = 10


@dataclass(frozen=True)
class TimelineEvent:
    at_seconds: float
    command: str


@dataclass(frozen=True)
class ExecutedEvent:
    event: TimelineEvent
    ran_at_seconds: float
    return_code: int


@dataclass(frozen=True)
class TimelineSettings:
    target_url: str = "http://localhost:8080"
    method: str = "GET"
    path: str = "/items"
    rate_per_second: float = 20.0
    duration_seconds: float = 40.0
    request_timeout_seconds: float = 5.0
    api_key: str | None = None
    events: tuple[TimelineEvent, ...] = ()
    output: Path | None = None


@dataclass(frozen=True)
class SecondSummary:
    second: int
    admitted: int
    rejected: int
    unavailable: int
    errors: int
    p95_milliseconds: float


def parse_event(text: str) -> TimelineEvent:
    """``"10=docker stop node"`` -> run ``docker stop node`` 10 s after the start."""
    at_seconds, _, command = text.partition("=")
    return TimelineEvent(float(at_seconds), command.strip())


async def send_or_record_error(
    session: aiohttp.ClientSession, target: RequestTarget, api_key: str
) -> ObservedResponse:
    """A failed request is a data point here, not a crash: status 0."""
    sent_at = time.perf_counter()
    try:
        return await send_request(session, target, api_key)
    except (aiohttp.ClientError, TimeoutError):
        return ObservedResponse(
            sent_at, time.perf_counter() - sent_at, STATUS_CLIENT_ERROR, CIMultiDict()
        )


async def send_and_collect(
    session: aiohttp.ClientSession,
    target: RequestTarget,
    api_key: str,
    responses: list[ObservedResponse],
) -> None:
    responses.append(await send_or_record_error(session, target, api_key))


async def send_steady_traffic(
    session: aiohttp.ClientSession, settings: TimelineSettings, started: float
) -> list[ObservedResponse]:
    target = RequestTarget(settings.method, settings.path)
    api_key = settings.api_key or create_api_key("timeline")
    responses: list[ObservedResponse] = []
    request_count = int(settings.rate_per_second * settings.duration_seconds)
    async with anyio.create_task_group() as task_group:
        for request_index in range(request_count):
            send_at = started + request_index / settings.rate_per_second
            await anyio.sleep(max(send_at - time.perf_counter(), 0.0))
            task_group.start_soon(send_and_collect, session, target, api_key, responses)
    return responses


async def run_events(
    events: Sequence[TimelineEvent], started: float, executed: list[ExecutedEvent]
) -> None:
    for event in sorted(events, key=lambda event: event.at_seconds):
        await anyio.sleep(max(started + event.at_seconds - time.perf_counter(), 0.0))
        ran_at = time.perf_counter() - started
        completed = await anyio.run_process(shlex.split(event.command), check=False)
        executed.append(ExecutedEvent(event, ran_at, completed.returncode))


async def run_timeline(
    settings: TimelineSettings,
) -> tuple[list[ObservedResponse], list[ExecutedEvent], float]:
    session_settings = HarnessSettings(
        target_url=settings.target_url, request_timeout_seconds=settings.request_timeout_seconds
    )
    executed: list[ExecutedEvent] = []
    async with create_http_session(session_settings) as session:
        await open_connections(session, 20, "/ping")
        started = time.perf_counter()
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(run_events, settings.events, started, executed)
            responses = await send_steady_traffic(session, settings, started)
    return responses, executed, started


def summarize_by_second(
    responses: Sequence[ObservedResponse], started: float
) -> list[SecondSummary]:
    by_second: dict[int, list[ObservedResponse]] = {}
    for response in responses:
        by_second.setdefault(int(response.sent_at - started), []).append(response)
    summaries = []
    for second in sorted(by_second):
        batch = by_second[second]
        statuses = [response.status_code for response in batch]
        latencies = sorted(response.elapsed_seconds for response in batch)
        p95 = statistics.quantiles(latencies, n=20)[-1] if len(latencies) > 1 else latencies[0]
        summaries.append(
            SecondSummary(
                second=second,
                admitted=statuses.count(STATUS_OK),
                rejected=statuses.count(STATUS_TOO_MANY_REQUESTS),
                unavailable=statuses.count(STATUS_SERVICE_UNAVAILABLE),
                errors=len(statuses)
                - statuses.count(STATUS_OK)
                - statuses.count(STATUS_TOO_MANY_REQUESTS)
                - statuses.count(STATUS_SERVICE_UNAVAILABLE),
                p95_milliseconds=p95 * 1000,
            )
        )
    return summaries


def render_timeline(
    settings: TimelineSettings, seconds: Sequence[SecondSummary], executed: Sequence[ExecutedEvent]
) -> str:
    lines = [
        f"# Outage timeline: {settings.method} {settings.path}",
        "",
        f"One API key at {settings.rate_per_second:g} requests/s for "
        f"{settings.duration_seconds:g} s against {settings.target_url}.",
        "",
        "| At (s) | Command | Exit code |",
        "|---|---|---|",
    ]
    lines += [
        f"| {e.ran_at_seconds:.1f} | `{e.event.command}` | {e.return_code} |" for e in executed
    ]
    lines += [
        "",
        "| Second | 200 | 429 | 503 | Errors | p95 ms |",
        "|---|---|---|---|---|---|",
    ]
    lines += [
        f"| {s.second} | {s.admitted} | {s.rejected} | {s.unavailable} | {s.errors} "
        f"| {s.p95_milliseconds:.0f} |"
        for s in seconds
    ]
    lines += ["", f"| Window ({ADMISSION_WINDOW_SECONDS} s) | Admitted |", "|---|---|"]
    by_window: dict[int, int] = {}
    for summary in seconds:
        window_index = summary.second // ADMISSION_WINDOW_SECONDS
        by_window[window_index] = by_window.get(window_index, 0) + summary.admitted
    lines += [
        f"| {index * ADMISSION_WINDOW_SECONDS}–{(index + 1) * ADMISSION_WINDOW_SECONDS} s "
        f"| {admitted} |"
        for index, admitted in sorted(by_window.items())
    ]
    return "\n".join(lines) + "\n"


def parse_settings(arguments: list[str] | None = None) -> TimelineSettings:
    defaults = TimelineSettings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", default=defaults.target_url)
    parser.add_argument("--method", default=defaults.method)
    parser.add_argument("--path", default=defaults.path)
    parser.add_argument("--rate", type=float, default=defaults.rate_per_second)
    parser.add_argument("--seconds", type=float, default=defaults.duration_seconds)
    parser.add_argument("--timeout", type=float, default=defaults.request_timeout_seconds)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--event", action="append", default=[], type=parse_event)
    parser.add_argument("--output", type=Path, default=None)
    parsed = parser.parse_args(arguments)
    return TimelineSettings(
        target_url=parsed.target,
        method=parsed.method,
        path=parsed.path,
        rate_per_second=parsed.rate,
        duration_seconds=parsed.seconds,
        request_timeout_seconds=parsed.timeout,
        api_key=parsed.api_key,
        events=tuple(parsed.event),
        output=parsed.output,
    )


def main(arguments: list[str] | None = None) -> str:
    settings = parse_settings(arguments)
    responses, executed, started = anyio.run(run_timeline, settings)
    report = render_timeline(settings, summarize_by_second(responses, started), executed)
    if settings.output is not None:
        settings.output.parent.mkdir(parents=True, exist_ok=True)
        settings.output.write_text(report, encoding="utf-8")
    print(report)
    return report


if __name__ == "__main__":
    main()
